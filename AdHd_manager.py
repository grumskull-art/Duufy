class ADHDStrategiApp:
    def __init__(self):
        self.strategier = {
            "fokus": [
                "Brug timer (Pomodoro: 25 min arbejde, 5 min pause)",
                "Fjern distraktioner fra dit arbejdsområde",
                "Lav en checklist over opgaver",
                "Opdel store opgaver i mindre dele"
            ],
            "organisation": [
                "Brug en kalender eller planner",
                "Sæt påmindelser på telefonen",
                "Lav rutiner for daglige opgaver",
                "Organisér ét område ad gangen"
            ],
            "søvn": [
                "Gå i seng på samme tid hver dag",
                "Undgå skærme 1 time før sengetid",
                "Skab en rolig søvnritual",
                "Brug mørke og køling på soveværelset"
            ],
            "stress": [
                "Øvelse eller motion dagligt",
                "Mindfulness eller meditation",
                "Tag pauser når du føler dig overwhelmet",
                "Tal med nogen du stoler på"
            ]
        }
    
    def vis_menu(self):
        print("\n=== ADHD Strategi App ===")
        print("1. Fokus strategier")
        print("2. Organisations strategier")
        print("3. Søvn strategier")
        print("4. Stress håndtering")
        print("5. Afslut")
    
    def vis_strategier(self, kategori):
        if kategori in self.strategier:
            print(f"\n--- {kategori.upper()} Strategier ---")
            for i, strategi in enumerate(self.strategier[kategori], 1):
                print(f"{i}. {strategi}")
        else:
            print("Kategori ikke fundet.")
    
    def start(self):
        while True:
            self.vis_menu()
            valg = input("\nVælg en option (1-5): ")
            
            if valg == "1":
                self.vis_strategier("fokus")
            elif valg == "2":
                self.vis_strategier("organisation")
            elif valg == "3":
                self.vis_strategier("søvn")
            elif valg == "4":
                self.vis_strategier("stress")
            elif valg == "5":
                print("Tak for at bruge ADHD Strategi App!")
                break
            else:
                print("Ugyldigt valg. Prøv igen.")

if __name__ == "__main__":
    app = ADHDStrategiApp()
    app.start()