"""
Image Service - Production-ready billede håndtering
- Hash-based caching
- Multiple resolutions support
- Category-based fallbacks
- CDN-ready struktur
"""
from pathlib import Path
from typing import Optional
from functools import lru_cache
import json
import hashlib

# Image configuration
IMAGE_BASE_URL = "/assets/images"  # Change to CDN URL in production
FALLBACK_IMAGES = {
    "Mejeriprodukter": "dairy.jpg",
    "Bageri": "bread.jpg",
    "Kød & Fisk": "meat.jpg",
    "Grøntsager": "vegetables.jpg",
    "Frugt": "fruit.jpg",
    "Drikkevarer": "drinks.jpg",
    "Snacks & Slik": "snacks.jpg",
    "Frost": "frozen.jpg",
    "Krydderier & Ingredienser": "spices.jpg",
    "Andre": "default.jpg"
}

# Load image map
IMAGE_MAP_FILE = Path(__file__).parent / "data" / "image_map.json"

@lru_cache(maxsize=1)
def _load_image_map() -> dict:
    """Load image mapping (cached)"""
    if IMAGE_MAP_FILE.exists():
        return json.loads(IMAGE_MAP_FILE.read_text(encoding="utf-8"))
    return {}

def get_image_url(product_name: str, category: str = "Andre", size: str = "medium") -> str:
    """
    Get image URL for product with smart fallback
    
    Args:
        product_name: Produktnavn (f.eks. "Sødmælk")
        category: Produktkategori for fallback
        size: Image size (thumbnail|medium|large)
    
    Returns:
        Image URL path
    """
    image_map = _load_image_map()
    
    # Normalize product name for lookup
    lookup_key = product_name.lower().strip()
    
    # Try exact match
    if lookup_key in image_map:
        img_data = image_map[lookup_key]
        if isinstance(img_data, dict):
            # Support multiple resolutions
            return f"{IMAGE_BASE_URL}/{img_data.get(size, img_data.get('medium', img_data['filename']))}"
        else:
            # Simple string filename
            return f"{IMAGE_BASE_URL}/{img_data}"
    
    # Fallback to category default
    category_img = FALLBACK_IMAGES.get(category, FALLBACK_IMAGES["Andre"])
    return f"{IMAGE_BASE_URL}/categories/{category_img}"

def get_product_hash(product_name: str) -> str:
    """Generate consistent hash for product (for cache keys)"""
    return hashlib.md5(product_name.lower().encode()).hexdigest()[:8]

@lru_cache(maxsize=256)
def image_exists(product_name: str) -> bool:
    """Check if product has custom image (cached)"""
    image_map = _load_image_map()
    return product_name.lower().strip() in image_map

def get_image_metadata(product_name: str) -> dict:
    """Get full image metadata for product"""
    image_map = _load_image_map()
    lookup_key = product_name.lower().strip()
    
    if lookup_key in image_map:
        img_data = image_map[lookup_key]
        if isinstance(img_data, dict):
            return {
                "has_custom_image": True,
                "thumbnail": f"{IMAGE_BASE_URL}/{img_data.get('thumbnail', img_data.get('filename'))}",
                "medium": f"{IMAGE_BASE_URL}/{img_data.get('medium', img_data.get('filename'))}",
                "large": f"{IMAGE_BASE_URL}/{img_data.get('large', img_data.get('filename'))}",
                "alt_text": product_name,
                "cache_key": get_product_hash(product_name)
            }
        else:
            url = f"{IMAGE_BASE_URL}/{img_data}"
            return {
                "has_custom_image": True,
                "thumbnail": url,
                "medium": url,
                "large": url,
                "alt_text": product_name,
                "cache_key": get_product_hash(product_name)
            }
    
    return {
        "has_custom_image": False,
        "thumbnail": f"{IMAGE_BASE_URL}/categories/default.jpg",
        "medium": f"{IMAGE_BASE_URL}/categories/default.jpg",
        "large": f"{IMAGE_BASE_URL}/categories/default.jpg",
        "alt_text": product_name,
        "cache_key": get_product_hash(product_name)
    }

# Preload check
if __name__ == "__main__":
    # Test cases
    print("Testing image service...")
    print(f"Sødmælk: {get_image_url('Sødmælk', 'Mejeriprodukter')}")
    print(f"Rugbrød: {get_image_url('Rugbrød', 'Bageri')}")
    print(f"Unknown: {get_image_url('Unknown Product', 'Andre')}")
    print(f"\nMetadata for Sødmælk: {get_image_metadata('Sødmælk')}")
