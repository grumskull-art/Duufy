# Jesper hus den 06,12,2025
voksne_pris = 359
børn_3_12_pris = 289
børn_0_3_pris = 0
blomsterpark_voksne = 50
blomsterpark_børn = 100
legeland_voksne = 60
legeland_børn = 150
piratshow_voksne = 50
piratshow_børn_0_3 = 0
piratshow_børn_3_12 = 75

def beregn_total_pris(antal_voksne, antal_børn_0_3, antal_børn_3_12, blomsterpark_voksne_antal, blomsterpark_børn_antal, legeland_voksne_antal, legeland_børn_antal, piratshow_voksne_antal, piratshow_børn_0_3_antal, piratshow_børn_3_12_antal):
    total_voksne = antal_voksne * voksne_pris
    total_børn_0_3 = antal_børn_0_3 * børn_0_3_pris
    total_børn_3_12 = antal_børn_3_12 * børn_3_12_pris
    total_pris = total_voksne + total_børn_0_3 + total_børn_3_12
    
    total_pris += (blomsterpark_voksne_antal * blomsterpark_voksne) + (blomsterpark_børn_antal * blomsterpark_børn)
    total_pris += (legeland_voksne_antal * legeland_voksne) + (legeland_børn_antal * legeland_børn)
    total_pris += (piratshow_voksne_antal * piratshow_voksne) + (piratshow_børn_0_3_antal * piratshow_børn_0_3) + (piratshow_børn_3_12_antal * piratshow_børn_3_12)
    
    return total_pris

def main():
    print("Velkommen til Jesper hus billetberegner!")
    antal_voksne = int(input("Antal voksne: "))
    antal_børn_0_3 = int(input("Antal børn 0-3 år: "))
    antal_børn_3_12 = int(input("Antal børn 3-12 år: "))
    
    piratshow = input("Ønsker I piratshow? (ja/nej): ")
    
    if piratshow.lower() == 'ja':
        piratshow_voksne_antal = int(input("Hvor mange voksne skal i piratshow: "))
        piratshow_børn_0_3_antal = int(input("Hvor mange børn 0-3 år skal i piratshow: "))
        piratshow_børn_3_12_antal = int(input("Hvor mange børn 3-12 år skal i piratshow: "))
    else:
        piratshow_voksne_antal = 0
        piratshow_børn_0_3_antal = 0
        piratshow_børn_3_12_antal = 0
    
    blomsterpark = input("Ønsker I blomsterpark? (ja/nej): ")
    
    if blomsterpark.lower() == 'ja':
        blomsterpark_voksne_antal = int(input("Hvor mange voksne skal i blomsterpark: "))
        blomsterpark_børn_antal = int(input("Hvor mange børn skal i blomsterpark: "))
    else:
        blomsterpark_voksne_antal = 0
        blomsterpark_børn_antal = 0
    
    legeland = input("Ønsker I legeland? (ja/nej): ")
    
    if legeland.lower() == 'ja':
        legeland_voksne_antal = int(input("Hvor mange voksne skal i legeland: "))
        legeland_børn_antal = int(input("Hvor mange børn skal i legeland: "))
    else:
        legeland_voksne_antal = 0
        legeland_børn_antal = 0
    
    total_pris = beregn_total_pris(antal_voksne, antal_børn_0_3, antal_børn_3_12, blomsterpark_voksne_antal, blomsterpark_børn_antal, legeland_voksne_antal, legeland_børn_antal, piratshow_voksne_antal, piratshow_børn_0_3_antal, piratshow_børn_3_12_antal)
    print(f"Den samlede pris for {antal_voksne} voksne, {antal_børn_0_3} børn 0-3 år og {antal_børn_3_12} børn 3-12 år er: {total_pris} DKK")

if __name__ == "__main__":
    main()