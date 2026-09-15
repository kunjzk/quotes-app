import io
import textwrap
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from PIL import Image, ImageDraw, ImageFont

from quotes.ocr_service import OCRResult, OCRService, build_ocr_result

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

    def test_crop_removes_text_outside_the_selection(self):
        # A photo of an open book: the facing page's text sits to the left.
        spread = Image.new('RGB', (2600, 800), 'white')
        draw = ImageDraw.Draw(spread)
        font = ImageFont.load_default(size=40)
        for i in range(6):
            draw.text((40, 120 + i * 60), 'Walrus pelican walrus', fill='black', font=font)
        spread.paste(render_text_image(size=(1500, 700)), (1000, 50))

        uncropped = OCRService.extract_text_from_image(to_jpeg(spread))
        self.assertIn('pelican', uncropped.text.lower())

        cropped = OCRService.extract_text_from_image(to_jpeg(spread), crop=(0.36, 0.0, 0.64, 1.0))
        self.assertReadsSample(cropped)
        self.assertNotIn('pelican', cropped.text.lower())

    def test_crop_applies_after_exif_rotation(self):
        # The browser shows the photo EXIF-rotated, so crop fractions refer to
        # that orientation, not the raw sensor pixels.
        upright = Image.new('RGB', (1800, 1400), 'white')
        upright.paste(render_text_image(), (0, 0))
        raw = upright.rotate(90, expand=True)  # stored sideways, tagged orientation 6
        result = OCRService.extract_text_from_image(
            to_jpeg(raw, orientation=6), crop=(0.0, 0.0, 1.0, 0.5)
        )
        self.assertReadsSample(result)

    def test_crop_image_uses_fractions_and_ignores_degenerate_boxes(self):
        image = Image.new('RGB', (1000, 500), 'white')
        self.assertEqual(OCRService.crop_image(image, (0.25, 0.1, 0.5, 0.8)).size, (500, 400))
        self.assertEqual(OCRService.crop_image(image, None).size, (1000, 500))
        self.assertEqual(OCRService.crop_image(image, (0.5, 0.5, 0.0, 0.0)).size, (1000, 500))

    def test_preprocess_collapses_blank_lines(self):
        raw = "  first  \n\n\n\nsecond\n   \nthird\n\n"
        self.assertEqual(
            OCRService.preprocess_extracted_text(raw),
            "first\n\nsecond\n\nthird",
        )


def tesseract_data(lines, word_height=40, char_width=20, conf=90):
    """
    Build image_to_data-style output. Each line is
    (block, par, line, left, top, "words on the line").
    """
    data = {k: [] for k in ('text', 'conf', 'block_num', 'par_num', 'line_num', 'left', 'top', 'width', 'height')}
    for block, par, line_num, left, top, text in lines:
        x = left
        for word in text.split():
            width = len(word) * char_width
            for key, value in (
                ('text', word), ('conf', conf), ('block_num', block), ('par_num', par),
                ('line_num', line_num), ('left', x), ('top', top), ('width', width), ('height', word_height),
            ):
                data[key].append(value)
            x += width + char_width
    return data


class LayoutReconstructionTest(SimpleTestCase):
    """Paragraphs come from positions on the page, not Tesseract's paragraph numbers."""

    def text(self, lines):
        return build_ocr_result(tesseract_data(lines)).text

    def test_lines_split_into_separate_blocks_rejoin_into_one_paragraph(self):
        # Photographed pages often come back with every line as its own
        # block/paragraph, which used to put a blank line after each one.
        lines = [
            (1, 1, 1, 100, 100, 'I went to the woods because I wished to live deliberately,'),
            (2, 1, 1, 100, 155, 'to front only the essential facts of life, and see if I could'),
            (3, 1, 1, 100, 210, 'not learn what it had to teach, and not, when I came to die,'),
            (4, 1, 1, 100, 265, 'discover that I had not lived.'),
        ]
        self.assertEqual(
            self.text(lines),
            'I went to the woods because I wished to live deliberately, to front only the essential '
            'facts of life, and see if I could not learn what it had to teach, and not, when I came '
            'to die, discover that I had not lived.',
        )

    def test_first_line_indent_starts_a_paragraph(self):
        lines = [
            (1, 1, 1, 100, 100, 'and suck out all the marrow of life, to live so sturdily and'),
            (1, 1, 2, 100, 155, 'Spartan-like as to put to rout all that was not life at all.'),
            (1, 1, 3, 160, 210, 'Our life is frittered away by detail. An honest man has'),
            (1, 1, 4, 100, 265, 'hardly need to count more than his ten fingers, or in extreme'),
        ]
        self.assertEqual(
            self.text(lines),
            'and suck out all the marrow of life, to live so sturdily and Spartan-like as to put to rout '
            'all that was not life at all.\n\nOur life is frittered away by detail. An honest man has '
            'hardly need to count more than his ten fingers, or in extreme',
        )

    def test_blank_line_gap_starts_a_paragraph(self):
        lines = [
            (1, 1, 1, 100, 100, 'Simplicity, simplicity, simplicity! I say, let your affairs'),
            (1, 1, 2, 100, 190, 'Heaven is under our feet as well as over our heads, and so it'),
        ]
        self.assertEqual(
            self.text(lines),
            'Simplicity, simplicity, simplicity! I say, let your affairs'
            '\n\nHeaven is under our feet as well as over our heads, and so it',
        )

    def test_short_line_ending_a_sentence_starts_a_paragraph_without_indent(self):
        lines = [
            (1, 1, 1, 100, 100, 'Block paragraphs in screenshots have no indent at all so'),
            (1, 1, 2, 100, 155, 'they end short.'),
            (1, 1, 3, 100, 210, 'The next paragraph starts flush left like every other one.'),
        ]
        self.assertEqual(
            self.text(lines),
            'Block paragraphs in screenshots have no indent at all so they end short.'
            '\n\nThe next paragraph starts flush left like every other one.',
        )

    def test_short_line_mid_sentence_stays_in_the_paragraph(self):
        lines = [
            (1, 1, 1, 100, 100, 'Ragged right text has lines of uneven length and'),
            (1, 1, 2, 100, 155, 'this one is short but'),
            (1, 1, 3, 100, 210, 'the sentence carries on to the next line of the page.'),
        ]
        self.assertEqual(
            self.text(lines),
            'Ragged right text has lines of uneven length and this one is short but '
            'the sentence carries on to the next line of the page.',
        )

    def test_side_by_side_columns_stay_separate(self):
        # Word fragments from the facing page, level with a line of the page itself.
        lines = [
            (1, 1, 1, 40, 100, 'ghts when'),
            (2, 1, 1, 700, 102, 'I went to the woods because I wished to live deliberately.'),
        ]
        self.assertEqual(
            self.text(lines),
            'ghts when\n\nI went to the woods because I wished to live deliberately.',
        )

    def test_words_hyphenated_across_lines_are_rejoined(self):
        lines = [
            (1, 1, 1, 100, 100, 'while I drink I see the sandy bottom and detect how shal-'),
            (1, 1, 2, 100, 155, 'low it is. Its thin current slides away, but the well-'),
            (1, 1, 3, 100, 210, 'Worn stones remain.'),
        ]
        # A capital after the hyphen suggests a real hyphen, so it is kept.
        self.assertEqual(
            self.text(lines),
            'while I drink I see the sandy bottom and detect how shallow it is. Its thin current '
            'slides away, but the well- Worn stones remain.',
        )

    def test_confidence_is_character_weighted(self):
        data = tesseract_data([(1, 1, 1, 100, 100, 'a')], conf=20)
        more = tesseract_data([(1, 1, 1, 100, 100, 'abcd')], conf=80)
        for key in data:
            data[key] += more[key]
        # 'a' (1 char at 20) and 'abcd' (4 chars at 80) on the same line.
        result = build_ocr_result(data)
        self.assertAlmostEqual(result.confidence, (20 * 1 + 80 * 4) / 5)
        self.assertEqual(result.word_count, 2)

    def test_ignores_structural_entries_and_empty_words(self):
        data = tesseract_data([(1, 1, 1, 100, 100, 'Stone by stone.')])
        for key, value in (('text', ''), ('conf', -1), ('block_num', 1), ('par_num', 0), ('line_num', 0),
                           ('left', 0), ('top', 0), ('width', 2000), ('height', 2000)):
            data[key].insert(0, value)
        self.assertEqual(build_ocr_result(data).text, 'Stone by stone.')

    def test_no_words_gives_empty_result(self):
        result = build_ocr_result(tesseract_data([]))
        self.assertEqual((result.text, result.confidence, result.word_count), ('', 0.0, 0))


class ImageUploadViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='reader', email='reader@example.com', password='pw'
        )
        self.client.login(username='reader', password='pw')
        self.url = reverse('quotes:image_upload')

    def upload(self, **extra):
        image = SimpleUploadedFile(
            'page.jpg', to_jpeg(render_text_image()).read(), content_type='image/jpeg'
        )
        return self.client.post(self.url, {'image': image, **extra})

    def test_crop_is_passed_to_ocr(self):
        with patch.object(
            OCRService, 'extract_text_from_image',
            return_value=OCRResult(text='Stone by stone.', confidence=91.4, word_count=3),
        ) as extract:
            response = self.upload(crop_x='0.3500', crop_y='0.0500', crop_w='0.6000', crop_h='0.9000')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(extract.call_args.kwargs['crop'], (0.35, 0.05, 0.6, 0.9))

    def test_no_crop_reads_the_whole_photo(self):
        with patch.object(
            OCRService, 'extract_text_from_image',
            return_value=OCRResult(text='Stone by stone.', confidence=91.4, word_count=3),
        ) as extract:
            self.upload()
        self.assertIsNone(extract.call_args.kwargs['crop'])

    def test_crop_rounding_past_the_edge_is_clamped(self):
        with patch.object(
            OCRService, 'extract_text_from_image',
            return_value=OCRResult(text='Stone by stone.', confidence=91.4, word_count=3),
        ) as extract:
            self.upload(crop_x='0.5000', crop_y='-0.0004', crop_w='0.5004', crop_h='1.0000')
        x, y, w, h = extract.call_args.kwargs['crop']
        self.assertEqual((x, y), (0.5, 0.0))
        self.assertLessEqual(x + w, 1.0)
        self.assertLessEqual(y + h, 1.0)

    def test_invalid_crops_are_rejected(self):
        cases = {
            'not a number': dict(crop_x='left', crop_y='0', crop_w='1', crop_h='1'),
            'partial': dict(crop_x='0.1'),
            'not finite': dict(crop_x='nan', crop_y='0', crop_w='0.5', crop_h='0.5'),
            'outside': dict(crop_x='0.8', crop_y='0', crop_w='0.5', crop_h='1'),
            'too small': dict(crop_x='0.1', crop_y='0.1', crop_w='0.01', crop_h='0.5'),
        }
        for label, crop in cases.items():
            with self.subTest(label), patch.object(OCRService, 'extract_text_from_image') as extract:
                response = self.upload(**crop)
                self.assertEqual(response.status_code, 400)
                self.assertIn('crop area', response.json()['error'])
                extract.assert_not_called()

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
        self.assertIn('No text could be found', response.json()['error'])
