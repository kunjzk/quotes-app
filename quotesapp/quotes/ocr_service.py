"""
OCR service for extracting text from images.
"""
import logging
from typing import Optional
from PIL import Image
import pytesseract
import io

logger = logging.getLogger(__name__)


class OCRService:
    """Service for extracting text from images using Tesseract OCR."""
    
    @staticmethod
    def extract_text_from_image(image_file) -> Optional[str]:
        """
        Extract text from an uploaded image file.
        
        Args:
            image_file: Django UploadedFile object or file-like object
            
        Returns:
            Extracted text as a string, or None if extraction fails
        """
        try:
            image = Image.open(image_file)
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            text = pytesseract.image_to_string(image, lang='eng')
            
            extracted_text = text.strip()
            
            logger.info(
                "Text extracted from image",
                extra={
                    "text_length": len(extracted_text),
                    "success": bool(extracted_text)
                }
            )
            
            return extracted_text if extracted_text else None
            
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}", exc_info=True)
            return None
    
    @staticmethod
    def preprocess_extracted_text(text: str) -> str:
        """
        Clean up extracted text by removing extra whitespace and normalizing line breaks.
        
        Args:
            text: Raw extracted text
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        lines = text.split('\n')
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        
        return '\n'.join(cleaned_lines)
