"""
OCR service for extracting text from images.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import pytesseract
from PIL import Image, ImageOps, ImageStat
from pytesseract import Output

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    text: str
    # Character-weighted mean of Tesseract's per-word confidence, 0-100.
    confidence: float
    # Extra rotation (degrees, counter-clockwise) applied on top of the
    # EXIF-corrected image to get the best read.
    rotation: int = 0
    word_count: int = 0


class OCRService:
    """Service for extracting text from images using Tesseract OCR."""

    # Tesseract's LSTM engine degrades on very large text; phone photos are
    # typically 3000-4000px on the long edge, far more than needed.
    MAX_DIMENSION = 2500
    # Below this, small screenshots/crops benefit from upscaling.
    MIN_DIMENSION = 1000

    # Reads below this confidence trigger rotation trials on the server and a
    # warning to the user in the UI.
    LOW_CONFIDENCE_THRESHOLD = 55.0

    # Tried in order of likelihood for phone photos when the upright read is poor.
    FALLBACK_ROTATIONS = (180, 90, 270)

    @staticmethod
    def load_image(image_file) -> Image.Image:
        """
        Open an uploaded image and normalise its orientation.

        Phone cameras usually store the sensor's raw pixels and record the
        intended display rotation in the EXIF Orientation tag. Browsers honour
        the tag when rendering, but PIL does not, so without this step
        Tesseract receives sideways or upside-down text.
        """
        image = Image.open(image_file)
        image = ImageOps.exif_transpose(image)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        return image

    @classmethod
    def prepare_for_ocr(cls, image: Image.Image) -> Image.Image:
        """
        Resize, greyscale, boost contrast and ensure dark-on-light polarity.
        """
        width, height = image.size
        longest = max(width, height)
        if longest > cls.MAX_DIMENSION:
            scale = cls.MAX_DIMENSION / longest
            image = image.resize(
                (round(width * scale), round(height * scale)), Image.LANCZOS
            )
        elif longest < cls.MIN_DIMENSION:
            scale = cls.MIN_DIMENSION / longest
            image = image.resize(
                (round(width * scale), round(height * scale)), Image.LANCZOS
            )

        grey = ImageOps.grayscale(image)
        grey = ImageOps.autocontrast(grey, cutoff=1)

        # Tesseract is trained on dark text over a light background. Book
        # covers and dark-mode screenshots are commonly the reverse.
        if ImageStat.Stat(grey).mean[0] < 128:
            grey = ImageOps.invert(grey)

        return grey

    @staticmethod
    def _ocr_with_confidence(image: Image.Image) -> OCRResult:
        """
        Run Tesseract once and reconstruct text with layout, plus a confidence score.

        Using image_to_data instead of image_to_string gives per-word
        confidence for free, so a single pass yields both.
        """
        data = pytesseract.image_to_data(image, lang='eng', output_type=Output.DICT)

        lines = {}
        total_chars = 0
        weighted_conf = 0.0
        word_count = 0

        for i, raw_word in enumerate(data['text']):
            word = raw_word.strip()
            conf = float(data['conf'][i])
            # conf is -1 for structural (non-word) entries.
            if not word or conf < 0:
                continue
            key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
            lines.setdefault(key, []).append(word)
            total_chars += len(word)
            weighted_conf += conf * len(word)
            word_count += 1

        if not word_count:
            return OCRResult(text='', confidence=0.0, word_count=0)

        text_lines = []
        previous_par = None
        for key in sorted(lines):
            par = key[:2]
            if previous_par is not None and par != previous_par:
                text_lines.append('')
            text_lines.append(' '.join(lines[key]))
            previous_par = par

        return OCRResult(
            text='\n'.join(text_lines),
            confidence=weighted_conf / total_chars,
            word_count=word_count,
        )

    @classmethod
    def extract_text_from_image(cls, image_file) -> Optional[OCRResult]:
        """
        Extract text from an uploaded image file.

        Args:
            image_file: Django UploadedFile object or file-like object

        Returns:
            OCRResult with the best read found, or None if nothing was
            extracted or an error occurred.
        """
        try:
            image = cls.load_image(image_file)
            prepared = cls.prepare_for_ocr(image)

            best = cls._ocr_with_confidence(prepared)

            # EXIF handles most rotation, but metadata is sometimes stripped
            # (screenshots, some messaging apps). A poor upright read is the
            # signal to try the other orientations.
            if best.confidence < cls.LOW_CONFIDENCE_THRESHOLD:
                for angle in cls.FALLBACK_ROTATIONS:
                    candidate = cls._ocr_with_confidence(
                        prepared.rotate(angle, expand=True)
                    )
                    candidate.rotation = angle
                    if candidate.confidence > best.confidence:
                        best = candidate

            logger.info(
                "Text extracted from image",
                extra={
                    "text_length": len(best.text),
                    "confidence": round(best.confidence, 1),
                    "rotation": best.rotation,
                    "word_count": best.word_count,
                },
            )

            return best if best.text else None

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}", exc_info=True)
            return None

    @staticmethod
    def preprocess_extracted_text(text: str) -> str:
        """
        Clean up extracted text by trimming lines and collapsing runs of blank lines.
        """
        if not text:
            return ""

        cleaned_lines = []
        for line in text.split('\n'):
            stripped = line.strip()
            if stripped:
                cleaned_lines.append(stripped)
            elif cleaned_lines and cleaned_lines[-1] != '':
                cleaned_lines.append('')

        while cleaned_lines and cleaned_lines[-1] == '':
            cleaned_lines.pop()

        return '\n'.join(cleaned_lines)
