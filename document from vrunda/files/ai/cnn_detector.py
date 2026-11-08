import os
from pathlib import Path
import numpy as np

cnn_model = None
cnn_model_loaded = False

def build_cnn_detector(input_shape=(224, 224, 3)):
    """
    Constructs the binary CNN polyp classification model.
    """
    import tensorflow as tf
    from tensorflow.keras import layers, models
    
    inputs = layers.Input(shape=input_shape, name="endoscopy_image_input")
    
    # Block 1
    x = layers.Conv2D(32, (3, 3), padding="same", name="conv1_1")(inputs)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.Conv2D(32, (3, 3), padding="same", name="conv1_2")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.MaxPooling2D((2, 2))(x)
    
    # Block 2
    x = layers.Conv2D(64, (3, 3), padding="same", name="conv2_1")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.Conv2D(64, (3, 3), padding="same", name="conv2_2")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.MaxPooling2D((2, 2))(x)
    
    # Block 3
    x = layers.Conv2D(128, (3, 3), padding="same", name="conv3_1")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.Conv2D(128, (3, 3), padding="same", name="conv3_2")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Activation("relu")(x)
    x = layers.MaxPooling2D((2, 2))(x)
    
    # Classifier Head
    x = layers.GlobalAveragePooling2D()(x)
    x = layers.Dense(128, activation="relu")(x)
    x = layers.Dropout(0.4)(x)
    outputs = layers.Dense(1, activation="sigmoid", name="polyp_probability")(x)
    
    model = models.Model(inputs=inputs, outputs=outputs, name="PolyScope_CNN_Detector")
    model.compile(
        optimizer="adam",
        loss="binary_crossentropy",
        metrics=["accuracy", tf.keras.metrics.AUC(name="auc")]
    )
    return model

def load_cnn_model(weights_path: Path):
    global cnn_model, cnn_model_loaded
    if cnn_model is not None:
        return cnn_model
    
    weights_path = Path(weights_path)
    if weights_path.is_file():
        try:
            import tensorflow as tf
            cnn_model = tf.keras.models.load_model(weights_path, compile=False)
            cnn_model_loaded = True
            print(f"[INFO] Loaded trained CNN detector from {weights_path}")
            return cnn_model
        except Exception as e:
            print(f"[WARN] Failed to load CNN weights from {weights_path}: {e}")
            cnn_model = None
            cnn_model_loaded = False
    return None

def predict_cnn(normalized_tensor, weights_path=None):
    """
    Inference with CNN classifier:
    Returns: (detected: bool, confidence: float, model_loaded: bool)
    """
    model = load_cnn_model(weights_path) if weights_path else cnn_model
    if model is None:
        return None, 0.0, False
    
    preds = model.predict(normalized_tensor, verbose=0)
    prob = float(preds[0][0])
    detected = prob >= 0.5
    confidence = prob if detected else (1.0 - prob)
    return detected, round(confidence * 100, 1), True
