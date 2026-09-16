"""
OCR service for extracting text from images.
"""
import logging
import re
from dataclasses import dataclass, field
from statistics import median
from typing import Optional

import pytesseract
from PIL import Image, ImageOps, ImageStat
from pytesseract import Output

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    # Paragraphs, with each paragraph's lines joined into flowing text.
    text: str
    # The same passage with every line kept, for lyrics and verse.
    lines: str = ""
    # Character-weighted mean of Tesseract's per-word confidence, 0-100.
    confidence: float = 0.0
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
    def crop_image(image: Image.Image, crop) -> Image.Image:
        """
        Crop to `crop`, a (left, top, width, height) box in fractions of the
        image (0-1), as chosen on the EXIF-corrected preview in the browser.
        """
        if crop is None:
            return image
        left, top, width, height = crop
        img_w, img_h = image.size
        box = (
            max(0, round(left * img_w)),
            max(0, round(top * img_h)),
            min(img_w, round((left + width) * img_w)),
            min(img_h, round((top + height) * img_h)),
        )
        if box[2] - box[0] < 1 or box[3] - box[1] < 1:
            return image
        return image.crop(box)

    @staticmethod
    def _ocr_with_confidence(image: Image.Image) -> OCRResult:
        """
        Run Tesseract once and reconstruct text with layout, plus a confidence score.

        Using image_to_data instead of image_to_string gives per-word
        confidence and positions for free, so a single pass yields both.
        """
        data = pytesseract.image_to_data(image, lang='eng', output_type=Output.DICT)
        return build_ocr_result(data)

    @classmethod
    def extract_text_from_image(cls, image_file, crop=None) -> Optional[OCRResult]:
        """
        Extract text from an uploaded image file.

        Args:
            image_file: Django UploadedFile object or file-like object
            crop: optional (left, top, width, height) in fractions of the image

        Returns:
            OCRResult with the best read found, or None if nothing was
            extracted or an error occurred.
        """
        try:
            image = cls.crop_image(cls.load_image(image_file), crop)
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


@dataclass
class _Line:
    words: list = field(default_factory=list)
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0

    @property
    def text(self) -> str:
        return ' '.join(self.words)

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


# A line ending in one of these can close a paragraph.
_TERMINAL_PUNCTUATION = re.compile(r'[.!?:;"\u201d\u2019)]$')
# "some-" at a line end followed by "thing" is one hyphenated word.
_HYPHENATED_END = re.compile(r'[A-Za-z]-$')


def build_ocr_result(data: dict) -> OCRResult:
    """
    Turn Tesseract's image_to_data output into flowing paragraphs and a
    character-weighted confidence score.
    """
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
        left, top = data['left'][i], data['top'][i]
        right, bottom = left + data['width'][i], top + data['height'][i]
        line = lines.get(key)
        if line is None:
            lines[key] = _Line([word], left, top, right, bottom)
        else:
            line.words.append(word)
            line.left, line.top = min(line.left, left), min(line.top, top)
            line.right, line.bottom = max(line.right, right), max(line.bottom, bottom)
        total_chars += len(word)
        weighted_conf += conf * len(word)
        word_count += 1

    if not word_count:
        return OCRResult(text='', lines='', confidence=0.0, word_count=0)

    ordered = [lines[key] for key in sorted(lines)]
    paragraphs = _group_paragraphs(ordered)
    return OCRResult(
        text='\n\n'.join(_join_lines(p) for p in paragraphs),
        lines='\n\n'.join('\n'.join(line.text for line in p) for p in paragraphs),
        confidence=weighted_conf / total_chars,
        word_count=word_count,
    )


def _group_paragraphs(lines: list) -> list:
    """
    Split lines into paragraphs using where they sit on the page rather than
    Tesseract's paragraph numbers, which fragment badly on photographed pages
    (often one "paragraph" per line). A new paragraph starts at a large
    vertical gap, a jump to another column, a first-line indent, or after a
    short line that ends a sentence.
    """
    line_height = median(line.height for line in lines) or 1
    paragraphs = [[lines[0]]]

    for i in range(1, len(lines)):
        prev, cur = lines[i - 1], lines[i]
        following = lines[i + 1] if i + 1 < len(lines) else None
        before_prev = lines[i - 2] if i >= 2 else None

        gap = cur.top - prev.bottom
        overlap = min(prev.right, cur.right) - max(prev.left, cur.left)
        narrower = max(1, min(prev.width, cur.width))

        new_paragraph = (
            # A blank line's worth of space, or the next line sits above this
            # one (a new column or block).
            gap > 0.75 * line_height
            or gap < -0.5 * line_height
            # Side by side rather than stacked: a different column.
            or overlap < 0.3 * narrower
            # First line indented relative to the lines around it.
            or _is_indented(cur, prev, following, line_height)
            # The previous line stopped well short of the text's right edge
            # at the end of a sentence.
            or _ends_short(prev, [n for n in (before_prev, cur) if n is not None])
        )

        if new_paragraph:
            paragraphs.append([cur])
        else:
            paragraphs[-1].append(cur)

    return paragraphs


def _is_indented(cur: _Line, prev: _Line, following: Optional[_Line], line_height: float) -> bool:
    threshold = 0.8 * line_height
    if cur.left - prev.left <= threshold:
        return False
    # Indented against the next line too, so this isn't a column that simply
    # starts further right. The last line has nothing to compare with.
    return following is None or cur.left - following.left > threshold


def _ends_short(prev: _Line, neighbours: list) -> bool:
    if not neighbours or not _TERMINAL_PUNCTUATION.search(prev.text):
        return False
    reference = max(neighbours, key=lambda line: line.right)
    return prev.right < reference.right - 0.3 * max(1, reference.width)


def _join_lines(lines: list) -> str:
    """Join a paragraph's lines into one line, rejoining words hyphenated across lines."""
    text = lines[0].text
    for line in lines[1:]:
        nxt = line.text
        if _HYPHENATED_END.search(text) and nxt[:1].islower():
            text = text[:-1] + nxt
        else:
            text = f'{text} {nxt}'
    return text
