import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from PIL import Image
from tensorflow import keras
from tensorflow.keras import layers

# Hent MNIST datasæt (håndskrevne tal)
(x_train, y_train), (x_test, y_test) = keras.datasets.mnist.load_data()

# Normaliser billederne (0-255 til 0-1)
x_train = x_train.astype("float32") / 255.0
x_test = x_test.astype("float32") / 255.0

# Byg neural netværk model
model = keras.Sequential(
    [
        layers.Flatten(input_shape=(28, 28)),
        layers.Dense(128, activation="relu"),
        layers.Dropout(0.2),
        layers.Dense(64, activation="relu"),
        layers.Dropout(0.2),
        layers.Dense(10, activation="softmax"),  # 10 klasser (0-9)
    ]
)

# Kompilér modellen
model.compile(
    optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"]
)

# Træn modellen
model.fit(x_train, y_train, epochs=10, batch_size=32, validation_split=0.1)

# Test modellen
test_loss, test_accuracy = model.evaluate(x_test, y_test)
print(f"Nøjagtighed: {test_accuracy * 100:.2f}%")


# Forudsig på dit eget billede
def forudsig_tal(billede_sti):
    img = Image.open(billede_sti).convert("L")  # Konverter til gråtoner
    img = img.resize((28, 28))
    img_array = np.array(img) / 255.0
    prediction = model.predict(np.array([img_array]))
    tal = np.argmax(prediction)
    return tal


# Brug det sådan:
# resultat = forudsig_tal("mit_billede.png")
# print(f"Genkendelse: {resultat}")
