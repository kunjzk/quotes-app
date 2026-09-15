import io
import textwrap
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from PIL import Image, ImageDraw, ImageFont

from quotes.ocr_service import OCRResult, OCRService

User = get_user_model()

SAMPLE_TEXT = (
    "A heart-stoppingly moving story. Murakami is, without "
    "a doubt, one of the world's finest novelists."
)

EXIF_ORIENTATION_TAG = 0x0112


def render_text_image(text=SAMPLE_TEXT, fg='black', bg='white', size=(1800, 700)):
    """Render wrapped text onto a solid background, like a photographed page."""
    font = ImageFont.load_default(size=40)
    image = Image.new('RGB', size, bg)
    draw = ImageDraw.Draw(image)
    y = 120
    for line in textwrap.wrap(text, 50):
        draw.text((120, y), line, fill=fg, font=font)
        y += 60
    return image


def to_jpeg(image, orientation=None):
    """Encode to JPEG, optionally tagging an EXIF orientation like a phone camera."""
    exif = image.getexif()
    if orientation is not None:
        exif[EXIF_ORIENTATION_TAG] = orientation
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', quality=90, exif=exif.tobytes())
    buffer.seek(0)
    return buffer


def normalise(text):
    return ' '.join(text.replace('\u2019', "'").split())


class OCRServiceTest(SimpleTestCase):
    """Exercises the real Tesseract binary against synthetic images."""

    def assertReadsSample(self, result):
        self.assertIsNotNone(result)
        self.assertIn("one of the world's finest novelists", normalise(result.text))
        self.assertGreater(result.confidence, OCRService.LOW_CONFIDENCE_THRESHOLD)

    def test_reads_upright_image(self):
        result = OCRService.extract_text_from_image(to_jpeg(render_text_image()))
        self.assertReadsSample(result)
        self.assertEqual(result.rotation, 0)

    def test_honours_exif_orientation(self):
        # Phones store the raw sensor pixels and describe the display rotation
        # in EXIF. Orientation 3 means "rotate 180 degrees to view".
        raw = render_text_image().rotate(180)
        result = OCRService.extract_text_from_image(to_jpeg(raw, orientation=3))
        self.assertReadsSample(result)
        self.assertEqual(result.rotation, 0)

    def test_honours_exif_orientation_sideways(self):
        # Orientation 6 means "rotate 90 degrees clockwise to view".
        raw = render_text_image().rotate(90, expand=True)
        result = OCRService.extract_text_from_image(to_jpeg(raw, orientation=6))
        self.assertReadsSample(result)
        self.assertEqual(result.rotation, 0)

    def test_recovers_upside_down_image_without_exif(self):
        raw = render_text_image().rotate(180)
        result = OCRService.extract_text_from_image(to_jpeg(raw))
        self.assertReadsSample(result)
        self.assertEqual(result.rotation, 180)

    def test_reads_light_text_on_dark_background(self):
        cover = render_text_image(fg='white', bg=(150, 30, 30))
        result = OCRService.extract_text_from_image(to_jpeg(cover))
        self.assertReadsSample(result)

    def test_downscales_large_images(self):
        big = Image.new('RGB', (4032, 3024), 'white')
        prepared = OCRService.prepare_for_ocr(big)
        self.assertEqual(max(prepared.size), OCRService.MAX_DIMENSION)

    def test_upscales_small_images(self):
        small = Image.new('RGB', (400, 300), 'white')
        prepared = OCRService.prepare_for_ocr(small)
        self.assertEqual(max(prepared.size), OCRService.MIN_DIMENSION)

    def test_returns_none_for_blank_image(self):
        blank = Image.new('RGB', (1200, 800), 'white')
        self.assertIsNone(OCRService.extract_text_from_image(to_jpeg(blank)))

    def test_returns_none_for_invalid_file(self):
        self.assertIsNone(OCRService.extract_text_from_image(io.BytesIO(b'not an image')))

    def test_preprocess_collapses_blank_lines(self):
        raw = "  first  \n\n\n\nsecond\n   \nthird\n\n"
        self.assertEqual(
            OCRService.preprocess_extracted_text(raw),
            "first\n\nsecond\n\nthird",
        )


class ImageUploadViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='reader', email='reader@example.com', password='pw'
        )
        self.client.login(username='reader', password='pw')
        self.url = reverse('quotes:image_upload')

    def upload(self):
        image = SimpleUploadedFile(
            'page.jpg', to_jpeg(render_text_image()).read(), content_type='image/jpeg'
        )
        return self.client.post(self.url, {'image': image})

    def test_response_includes_confidence_when_reliable(self):
        with patch.object(
            OCRService, 'extract_text_from_image',
            return_value=OCRResult(text='Stone by stone.', confidence=91.4, word_count=3),
        ):
            response = self.upload()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['text'], 'Stone by stone.')
        self.assertEqual(data['confidence'], 91.4)
        self.assertFalse(data['low_confidence'])

    def test_response_flags_low_confidence(self):
        with patch.object(
            OCRService, 'extract_text_from_image',
            return_value=OCRResult(text='S,Pj1om ay}', confidence=31.0, word_count=2),
        ):
            response = self.upload()
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['low_confidence'])

    def test_no_text_returns_400(self):
        with patch.object(OCRService, 'extract_text_from_image', return_value=None):
            response = self.upload()
        self.assertEqual(response.status_code, 400)
        self.assertIn('No text could be extracted', response.json()['error'])
