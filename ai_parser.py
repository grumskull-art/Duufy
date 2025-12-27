"""
AI-powered parser til indkøbslister
Bruger lokal regex først, falder tilbage til Claude API ved usikkerhed
"""

import re
import os
import json
from typing import List, Dict, Optional
from difflib import get_close_matches

# Load .env fil
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv ikke installeret, brug miljøvariabler direkte

# Prøv at importere Anthropic (valgfri)
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("⚠️ Anthropic ikke installeret - kun lokal parsing tilgængelig")

# Kategorier til varer
CATEGORIES = {
    # Mejeri
    'mælk': 'mejeri', 'letmælk': 'mejeri', 'minimælk': 'mejeri', 'sødmælk': 'mejeri',
    'smør': 'mejeri', 'ost': 'mejeri', 'fløde': 'mejeri', 'piskefløde': 'mejeri',
    'yoghurt': 'mejeri', 'skyr': 'mejeri', 'cremefraiche': 'mejeri',
    'kærnemælk': 'mejeri', 'ymer': 'mejeri', 'mozzarella': 'mejeri',
    # Kød
    'kylling': 'kød', 'oksekød': 'kød', 'hakket': 'kød', 'hakkekød': 'kød',
    'svinekød': 'kød', 'bacon': 'kød', 'pølser': 'kød', 'hamburgerryg': 'kød',
    'rullepølse': 'kød', 'leverpostej': 'kød', 'skinke': 'kød',
    'medister': 'kød', 'kalvekød': 'kød', 'lammekød': 'kød',
    # Fisk
    'laks': 'fisk', 'tun': 'fisk', 'torsk': 'fisk', 'rejer': 'fisk',
    # Brød
    'brød': 'bager', 'rugbrød': 'bager', 'franskbrød': 'bager', 'boller': 'bager',
    # Grøntsager
    'kartofler': 'grønt', 'kartoffel': 'grønt', 'løg': 'grønt', 'hvidløg': 'grønt',
    'gulerødder': 'grønt', 'gulerod': 'grønt', 'tomater': 'grønt', 'tomat': 'grønt',
    'agurk': 'grønt', 'salat': 'grønt', 'peberfrugt': 'grønt', 'broccoli': 'grønt',
    # Frugt
    'æbler': 'frugt', 'æble': 'frugt', 'bananer': 'frugt', 'banan': 'frugt',
    'appelsiner': 'frugt', 'appelsin': 'frugt', 'pærer': 'frugt', 'citroner': 'frugt',
    # Drikkevarer
    'juice': 'drikkevarer', 'cola': 'drikkevarer', 'sodavand': 'drikkevarer',
    'øl': 'drikkevarer', 'vin': 'drikkevarer', 'vand': 'drikkevarer',
    'kaffe': 'drikkevarer', 'te': 'drikkevarer',
    # Kolonial
    'pasta': 'kolonial', 'ris': 'kolonial', 'mel': 'kolonial', 'sukker': 'kolonial',
    'salt': 'kolonial', 'olie': 'kolonial', 'ketchup': 'kolonial', 'sennep': 'kolonial',
    'mayonnaise': 'kolonial', 'remoulade': 'kolonial',
    # Husholdning
    'toiletpapir': 'husholdning', 'køkkenrulle': 'husholdning', 'sæbe': 'husholdning',
    # Æg
    'æg': 'æg'
}

# Standard mængder per kategori/vare
DEFAULT_QUANTITIES = {
    'mejeri': '1 L', 'kød': '500 g', 'fisk': '400 g', 'bager': '1 stk',
    'grønt': '1 stk', 'frugt': '1 stk', 'drikkevarer': '1 L',
    'kolonial': '1 stk', 'husholdning': '1 pk', 'æg': '10 stk',
    # Specifikke varer
    'smør': '250 g', 'ost': '400 g', 'bacon': '1 pk', 'pølser': '1 pk',
    'kartofler': '1 kg', 'løg': '1 net', 'æbler': '1 kg', 'bananer': '1 bundt',
    'pasta': '500 g', 'ris': '1 kg', 'mel': '1 kg', 'sukker': '1 kg',
}

# Kendt produktliste til fuzzy matching
KNOWN_PRODUCTS = list(CATEGORIES.keys())

# Forkortelser og almindelige stavefejl
PRODUCT_ALIASES = {
    'hambo': 'hamburgerryg',
    'remu': 'remoulade',
    'karto': 'kartofler',
    'toma': 'tomater',
    'gule': 'gulerødder',
    'sømælk': 'sødmælk',
    'smæølk': 'sødmælk',
    'piskflø': 'piskefløde',
    'rugbrø': 'rugbrød',
    'franskbrø': 'franskbrød',
    'lever': 'leverpostej',
    'rulle': 'rullepølse',
}

def fuzzy_correct(word: str) -> str:
    """Prøv at rette stavefejl og forkortelser med fuzzy matching"""
    word_lower = word.lower()
    
    # Check direkte aliases først
    if word_lower in PRODUCT_ALIASES:
        return PRODUCT_ALIASES[word_lower]
    
    # Brug fuzzy matching på kendte produkter
    matches = get_close_matches(word_lower, KNOWN_PRODUCTS, n=1, cutoff=0.7)
    if matches:
        return matches[0]
    
    return word

# Mængde-mønster - mere præcist
AMOUNT_PATTERN = re.compile(
    r"^(\d+(?:[.,]\d+)?)\s*(l|liter|ml|dl|cl|stk|stykker?|pakke|pakker|pk|poser?|g|gram|kg|kilo|fl|flaske|flasker|ds|dåse|dåser|bundt|net)?\s+",
    re.IGNORECASE
)

def get_category(item_name: str) -> str:
    """Find kategori for en vare"""
    item_lower = item_name.lower()
    for key, category in CATEGORIES.items():
        if key in item_lower:
            return category
    return 'andet'

def get_default_quantity(item_name: str) -> str:
    """Gæt standard mængde for en vare"""
    item_lower = item_name.lower()
    
    # Tjek specifikke varer først
    for key, qty in DEFAULT_QUANTITIES.items():
        if key in item_lower:
            return qty
    
    # Ellers brug kategori
    category = get_category(item_name)
    return DEFAULT_QUANTITIES.get(category, '1 stk')

def smart_split_by_products(text: str) -> List[str]:
    """Splitter tekst ved kendte produkter for at adskille varer uden separator"""
    words = text.strip().split()
    if len(words) <= 2:
        return [text]
    
    parts = []
    current_part = []
    last_product_idx = -1
    
    for i, word in enumerate(words):
        # Check om ordet er et kendt produkt
        is_product = any(word == p or word.startswith(p) or p.startswith(word) 
                        for p in CATEGORIES.keys())
        
        # Check om næste ord starter en ny mængde
        next_word = words[i + 1] if i < len(words) - 1 else ''
        next_is_quantity = bool(re.match(r'^(\d+|en|et|to|tre|fire|fem|halvanden)$', next_word, re.IGNORECASE))
        next_is_product = any(next_word == p or next_word.startswith(p) or p.startswith(next_word) 
                              for p in CATEGORIES.keys())
        
        current_part.append(word)
        
        if is_product:
            last_product_idx = len(current_part) - 1
            
            # Hvis næste ord er mængde eller nyt produkt, afslut denne del
            if next_is_quantity or (next_is_product and i < len(words) - 1):
                parts.append(' '.join(current_part))
                current_part = []
                last_product_idx = -1
    
    # Tilføj resterende ord
    if current_part:
        parts.append(' '.join(current_part))
    
    return parts if parts else [text]

def local_parse(text: str) -> List[Dict]:
    """Parser tekst med regex - hurtig lokal parsing"""
    text = text.lower().strip()
    
    # Fjern fyldord fra starten - MEGET mere omfattende
    fillers = [
        r"^(øh|ehm|øhm|nå|nåh|altså|ikke|jo|bare)\s+",
        r"^(jeg skal have|vi skal have|skal have|jeg skal|vi skal)\s+",
        r"^(jeg|vi|man|den|det|de|der|den der|det der|de der)\s+",
        r"^(det der|ham der|hende der|den slags|du ved|jeg tænker)\s+",
        r"^(sku ha|sku have|ska ha|ska have)\s+",  # Slang/dialekt versioner
        r"^(skal have|skal bruge|skal købe|mangler|vi mangler)\s+",
        r"^(noget|lidt|lidt af|lidt af det|nogen|nogle)\s+",
        r"^(tilføj|køb|hent|tag|skriv|sæt)\s+",
        r"^(en|et|den|det)\s+(?!liter|kilo|kg|l\s)",  # Men ikke før enheder
    ]
    
    # Kør fyldords-fjernelse flere gange for at fange alle
    for _ in range(3):  # Max 3 iterationer
        old_text = text
        for filler in fillers:
            text = re.sub(filler, "", text, flags=re.IGNORECASE)
        if text == old_text:  # Ingen ændringer mere
            break
    
    # Split på eksplicitte separatorer
    parts = re.split(r"\s+og\s+|\s*,\s*|\s+samt\s+|\s+plus\s+", text)
    
    # For hver del, prøv at splitte på kendte produkter
    all_parts = []
    for part in parts:
        all_parts.extend(smart_split_by_products(part))
    
    parsed_items = []
    
    # Ordtal til tal mapping
    word_to_num = {
        'en': '1', 'et': '1', 'to': '2', 'tre': '3', 'fire': '4', 'fem': '5',
        'seks': '6', 'syv': '7', 'otte': '8', 'ni': '9', 'ti': '10',
        'halvanden': '1.5', 'halvandet': '1.5'
    }
    
    for part in all_parts:
        part = part.strip()
        if not part or len(part) < 2:
            continue
        
        item_name = part
        quantity = ""
        
        # Prøv specielle mønstre først
        
        # "tre/fire/fem kilo/liter X" (ordtal + enhed)
        ordtal_match = re.match(r"^(en|et|to|tre|fire|fem|seks|syv|otte|ni|ti|halvanden|halvandet)\s+(liter|l|kilo|kg|gram|g)\s+(.+)$", part, re.IGNORECASE)
        if ordtal_match:
            num_word = ordtal_match.group(1).lower()
            unit = ordtal_match.group(2).lower()
            item_name = ordtal_match.group(3).strip()
            
            # Konverter ordtal til tal
            num = word_to_num.get(num_word, num_word)
            
            # Normaliser enhed
            if unit in ['l', 'liter']:
                unit = 'L'
            elif unit in ['kg', 'kilo']:
                unit = 'kg'
            elif unit in ['g', 'gram']:
                unit = 'g'
            
            quantity = f"{num} {unit}"
        
        # "halvanden liter/kilo X"
        elif re.match(r"^(halvanden|halvandet)\s+(liter|l|kilo|kg)\s+", part, re.IGNORECASE):
            halvanden_match = re.match(r"^(halvanden|halvandet)\s+(liter|l|kilo|kg)\s+(.+)$", part, re.IGNORECASE)
            if halvanden_match:
                unit = halvanden_match.group(2)
                item_name = halvanden_match.group(3).strip()
                unit_norm = "L" if unit.lower() in ['l', 'liter'] else "kg"
                quantity = f"1.5 {unit_norm}"
        
        # "en/et/halv/halvt liter/kilo X"
        elif re.match(r"^(en|et|halv|halvt)\s+(liter|l|kilo|kg)\s+", part, re.IGNORECASE):
            unit_match = re.match(r"^(en|et|halv|halvt)\s+(liter|l|kilo|kg)\s+(.+)$", part, re.IGNORECASE)
            if unit_match:
                quantity_word = unit_match.group(1).lower()
                unit_word = unit_match.group(2).lower()
                item_name = unit_match.group(3).strip()
                
                # Bestem mængde
                if quantity_word in ['halv', 'halvt']:
                    num = '0.5'
                else:
                    num = '1'
                
                if unit_word in ['liter', 'l']:
                    quantity = f"{num} L"
                elif unit_word in ['kilo', 'kg']:
                    quantity = f"{num} kg"
        
        # "X l/liter/kg/stk Y"
        elif re.match(r"^\d", part):
            amount_match = AMOUNT_PATTERN.match(part)
            if amount_match:
                num = amount_match.group(1)
                unit = amount_match.group(2) or "stk"
                # Normaliser enhed
                unit_lower = unit.lower()
                if unit_lower in ['l', 'liter']:
                    unit = 'L'
                elif unit_lower in ['kg', 'kilo']:
                    unit = 'kg'
                elif unit_lower in ['g', 'gram']:
                    unit = 'g'
                elif unit_lower in ['ml', 'milliliter']:
                    unit = 'ml'
                elif unit_lower in ['dl', 'deciliter']:
                    unit = 'dl'
                elif unit_lower in ['stk', 'stykker', 'stykke']:
                    unit = 'stk'
                elif unit_lower in ['pk', 'pakke', 'pakker']:
                    unit = 'pk'
                    
                quantity = f"{num} {unit}"
                # Resten er item_name
                item_name = part[amount_match.end():].strip()
        
        # Ryd GRUNDIGT op i item_name - fjern alle fyldord
        item_name = re.sub(r"^(en|et|den|det|noget|nogen|nogle|lidt|den der|det der)\s+", "", item_name, flags=re.IGNORECASE)
        item_name = re.sub(r"^(den|det|der)\s+", "", item_name, flags=re.IGNORECASE)
        item_name = item_name.strip()
        
        if not item_name:
            continue
        
        # Prøv fuzzy correction på produktnavnet
        item_name = fuzzy_correct(item_name)
        
        # Sæt default mængde hvis ikke fundet
        if not quantity:
            quantity = get_default_quantity(item_name)
        
        # Find kategori
        category = get_category(item_name)
        
        parsed_items.append({
            "item": item_name.capitalize(),
            "quantity": quantity,
            "category": category
        })
    
    # Fjern duplikater - behold første forekomst
    seen = set()
    unique_items = []
    for item in parsed_items:
        item_key = item["item"].lower()
        if item_key not in seen:
            seen.add(item_key)
            unique_items.append(item)
    
    return unique_items

def opus_parse(text: str) -> List[Dict]:
    """Parser tekst med Claude API - for komplekse sætninger"""
    if not ANTHROPIC_AVAILABLE:
        return []
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️ ANTHROPIC_API_KEY ikke sat")
        return []
    
    try:
        client = Anthropic(api_key=api_key)
        
        prompt = f"""Du er en intelligent dansk indkøbsassistent. Brugeren taler ofte UTYDELIGT med dårligt/mumlet dansk.
Dit job: Forstå hvad de MENER og udtræk kun de relevante produkter.

🎯 HOVEDOPGAVE:
- Parser utydelig tale, stavefejl, afbrudte ord
- Gæt det mest sandsynlige produkt ved tvivl
- Ignorer ALT der ikke er produkter

❌ FJERN ALTID:
- Fyldord: "jeg skal have", "vi mangler", "skal købe"
- Pejleord: "den der", "det der", "ham der", "du ved"
- Samtale: "øh", "ehm", "altså", "ikke", "jo"
- Gentagelser: "mælk mælk mælk" → kun én "Mælk"
- Mumlen og pauser

✅ RET AUTOMATISK:
- "sømælk", "smæølk" → "Sødmælk"
- "rugbrø" → "Rugbrød"
- "hambo" → "Hamburgerryg"
- "remu" → "Remoulade"
- "piskflø" → "Piskefløde"
- "karto" → "Kartofler"

📝 EKSEMPLER:
"jæ ska den der smæølk" → Sødmælk (1 L)
"altså eh rugbrø rugbrød og mælk" → Rugbrød (1 stk), Mælk (1 L)
"øh jeg tænker lidt af det der hambo" → Hamburgerryg (1 pk)
"halv liter piskflø" → Piskefløde (0.5 L)
"tre kilo karto" → Kartofler (3 kg)
"smø smø smør" → Smør (250 g)  [kun én gang!]
"hambo og den der med remu" → Hamburgerryg (1 pk), Remoulade (1 stk)

📦 KATEGORIER:
mejeri, kød, fisk, bager, grønt, frugt, drikkevarer, kolonial, husholdning, æg, andet

🔧 OUTPUT (KUN JSON):
[
  {{"item": "Produktnavn", "quantity": "1 enhed", "category": "kategori"}}
]

🎤 BRUGERENS UTYDELIGE TALE:
"{text}"

RETURNÉR KUN JSON!"""
        
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",  # Bedre kvalitet, stadig billig
            max_tokens=800,
            temperature=0.3,  # Lav temperatur for konsistens
            messages=[{"role": "user", "content": prompt}]
        )
        
        result_text = response.content[0].text.strip()
        
        # Fjern eventuelle markdown code blocks
        if result_text.startswith("```"):
            result_text = re.sub(r"^```(?:json)?\n?", "", result_text)
            result_text = re.sub(r"\n?```$", "", result_text)
        
        parsed = json.loads(result_text)
        
        # Valider at det er en liste
        if not isinstance(parsed, list):
            print(f"⚠️ AI returnerede ikke en liste: {type(parsed)}")
            return []
        
        # Valider hvert item
        valid_items = []
        for item in parsed:
            if isinstance(item, dict) and "item" in item and "quantity" in item and "category" in item:
                valid_items.append(item)
            else:
                print(f"⚠️ Ugyldigt item fra AI: {item}")
        
        return valid_items
        
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON parse fejl: {e}")
        print(f"   Raw response: {result_text[:200]}...")
        return []
    except Exception as e:
        print(f"⚠️ Claude API fejl: {e}")
        return []

def smart_parse(text: str, force_ai: bool = False) -> Dict:
    """
    Smart parser - prøver lokal først, bruger AI ved usikkerhed
    
    Returns:
        Dict med 'items' (liste), 'method' ('local' eller 'ai'), og 'confidence'
    """
    # Prøv lokal parsing først
    local_result = local_parse(text)
    
    # Heuristik: Er vi sikre på resultatet?
    all_unknown = all(item["category"] == "andet" for item in local_result) if local_result else True
    short_input = len(text.split()) <= 2
    has_items = len(local_result) > 0
    very_short = len(text.split()) < 4  # Meget korte input er ofte uklare
    
    confidence = "high"
    if all_unknown and has_items:
        confidence = "low"
    elif not has_items:
        confidence = "none"
    
    # Brug AI hvis vi er usikre eller force_ai er True
    # Ved meget korte sætninger (<4 ord) eller ingen items - brug AI
    use_ai = force_ai or (confidence in ["low", "none"] and ANTHROPIC_AVAILABLE)
    if not has_items or all_unknown or very_short:
        use_ai = force_ai or ANTHROPIC_AVAILABLE
    
    if use_ai and not short_input:
        ai_result = opus_parse(text)
        if ai_result:
            return {
                "items": ai_result,
                "method": "ai",
                "confidence": "high",
                "original_text": text
            }
    
    # Returner lokal resultat
    return {
        "items": local_result,
        "method": "local",
        "confidence": confidence,
        "original_text": text
    }

# Test
if __name__ == "__main__":
    test_phrases = [
        # Grundlæggende
        "2 liter mælk",
        "vi mangler mælk og brød",
        "et kilo kartofler hamburgerryg og remoulade",
        
        # Med fyldord
        "jeg skal have den der sødmælk",
        "vi mangler noget rugbrød",
        "skal have øh tre kilo kartofler",
        
        # Komplekse
        "halvanden liter mælk og 3 bananer",
        "skal have noget kaffe og toiletpapir",
        "den der remoulade og det der øh bacon",
        
        # Edge cases
        "det der",  # Meget vagt
        "jeg skal have noget",  # Intet produkt
        "sødmælk",  # Simpelt
    ]
    
    print("🧪 Testing AI Parser\n" + "="*50)
    for phrase in test_phrases:
        result = smart_parse(phrase, force_ai=False)
        print(f"\n📝 '{phrase}'")
        print(f"   Metode: {result['method']} | Tillid: {result['confidence']}")
        if result['items']:
            for item in result['items']:
                print(f"   ✓ {item['item']}: {item['quantity']} ({item['category']})")
        else:
            print("   ✗ Ingen varer fundet")
