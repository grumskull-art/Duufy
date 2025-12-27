# Assets README

## Billede Struktur

Dette folder indeholder produktbilleder til Duufy appen.
*Do you often forget? Duufy don't*

### Struktur:
```
assets/
  images/
    soedmaelk.jpg          # Produktspecifikt billede
    rugbroed.jpg
    smoer.jpg
    ...
    categories/            # Fallback billeder per kategori
      dairy.jpg            # Mejeri default
      bread.jpg            # Bageri default
      meat.jpg             # Kød default
      vegetables.jpg       # Grønt default
      fruit.jpg            # Frugt default
      drinks.jpg           # Drikkevarer default
      snacks.jpg           # Snacks default
      frozen.jpg           # Frost default
      spices.jpg           # Krydderier default
      default.jpg          # Global fallback
```

### Anbefalinger:

**Produktbilleder:**
- Format: JPG/WebP
- Resolution: 
  - Thumbnail: 150x150px
  - Medium: 400x400px
  - Large: 800x800px
- Max filstørrelse: 100KB per billede
- Baggrund: Hvid eller transparent
- Naming: lowercase, uden special chars (sødmælk → soedmaelk.jpg)

**CDN Integration:**
Skift `IMAGE_BASE_URL` i image_service.py til din CDN URL:
```python
IMAGE_BASE_URL = "https://cdn.duufy.app/images"
```

**Billede kilde:**
1. **Fødevareproducenter:** Mange brands tilbyder gratis produktbilleder
2. **Supermarked APIs:** Coop, Salling Group har produktdata
3. **Open Food Facts:** Open database med produktbilleder
4. **Egen fotografering:** Tag billeder af produkter i butik

### Placeholder Billeder:
For development kan du bruge:
- https://via.placeholder.com/400x400/EEEEEE/666666?text=Sødmælk
- https://placehold.co/400x400/png?text=Product

Eller generer simple colored boxes som placeholders indtil rigtige billeder er klar.
