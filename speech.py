import speech_recognition as sr

def recognize_speech():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎤 Sig noget…")
        audio = r.listen(source)
        try:
            text = r.recognize_google(audio, language="da-DK")
            print(f"🗣️ Du sagde: {text}")
            return text
        except Exception as e:
            print("❌ Kunne ikke genkende tale:", e)
            return None

if __name__ == "__main__":
    recognize_speech()
