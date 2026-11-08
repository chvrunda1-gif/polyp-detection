import os
from pathlib import Path
import numpy as np
import cv2

unet_model = None
unet_model_loaded = False

def dice_coef(y_true, y_pred, smooth=1.0):
    import tensorflow as tf
    y_true_f = tf.keras.backend.flatten(y_true)
    y_pred_f = tf.keras.backend.flatten(y_pred)
    intersection = tf.keras.backend.sum(y_true_f * y_pred_f)
    return (2.0 * intersection + smooth) / (tf.keras.backend.sum(y_true_f) + tf.keras.backend.sum(y_pred_f) + smooth)

def dice_loss(y_true, y_pred):
    return 1.0 - dice_coef(y_true, y_pred)

def bce_dice_loss(y_true, y_pred):
    import tensorflow as tf
    return tf.keras.losses.binary_crossentropy(y_true, y_pred) + dice_loss(y_true, y_pred)

def build_unet_segmenter(input_shape=(224, 224, 3)):
    """
    Constructs the U-Net architecture with skip connections for polyp segmentation.
    """
    import tensorflow as tf
    from tensorflow.keras import layers, models
    
    inputs = layers.Input(shape=input_shape, name="endoscopy_image_input")
    skips = []
    x = inputs

    # Encoder
    for filters in (32, 64, 128, 256):
        x = layers.Conv2D(filters, (3, 3), padding="same", activation="relu")(x)
        x = layers.BatchNormalization()(x)
        x = layers.Conv2D(filters, (3, 3), padding="same", activation="relu")(x)
        x = layers.BatchNormalization()(x)
        skips.append(x)
        x = layers.MaxPooling2D((2, 2))(x)

    # Bottleneck
    x = layers.Conv2D(512, (3, 3), padding="same", activation="relu")(x)
    x = layers.BatchNormalization()(x)
    x = layers.Conv2D(512, (3, 3), padding="same", activation="relu")(x)
    x = layers.BatchNormalization()(x)

    # Decoder
    for filters, skip in zip((256, 128, 64, 32), reversed(skips)):
        x = layers.UpSampling2D((2, 2), interpolation="bilinear")(x)
        x = layers.Concatenate()([x, skip])
        x = layers.Conv2D(filters, (3, 3), padding="same", activation="relu")(x)
        x = layers.BatchNormalization()(x)
        x = layers.Conv2D(filters, (3, 3), padding="same", activation="relu")(x)
        x = layers.BatchNormalization()(x)

    outputs = layers.Conv2D(1, (1, 1), activation="sigmoid", name="polyp_segmentation_mask")(x)
    model = models.Model(inputs=inputs, outputs=outputs, name="PolyScope_UNet_Segmenter")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),
        loss=bce_dice_loss,
        metrics=[dice_coef, tf.keras.metrics.BinaryIoU(target_class_ids=[1], threshold=0.5, name="iou")]
    )
    return model

def load_unet_model(weights_path: Path):
    global unet_model, unet_model_loaded
    if unet_model is not None:
        return unet_model
    
    weights_path = Path(weights_path)
    if weights_path.is_file():
        try:
            import tensorflow as tf
            unet_model = tf.keras.models.load_model(
                weights_path,
                custom_objects={"dice_coef": dice_coef, "bce_dice_loss": bce_dice_loss},
                compile=False
            )
            unet_model_loaded = True
            print(f"[INFO] Loaded trained U-Net segmenter from {weights_path}")
            return unet_model
        except Exception as e:
            print(f"[WARN] Failed to load U-Net weights from {weights_path}: {e}")
            unet_model = None
            unet_model_loaded = False
    return None

def predict_unet(normalized_tensor, weights_path=None, threshold=0.5):
    """
    Inference with U-Net:
    Returns: (mask_binary: np.ndarray, confidence: float, bbox: tuple, model_loaded: bool)
    """
    model = load_unet_model(weights_path) if weights_path else unet_model
    if model is None:
        return None, 0.0, None, False
    
    pred = model.predict(normalized_tensor, verbose=0)[0, :, :, 0]
    binary_mask = (pred >= threshold).astype(np.uint8) * 255
    
    # Find contours
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_contours = [c for c in contours if cv2.contourArea(c) >= 48]
    
    if not valid_contours:
        return binary_mask, float(np.max(pred)), None, True
    
    largest = max(valid_contours, key=cv2.contourArea)
    bbox = cv2.boundingRect(largest) # x, y, w, h
    return binary_mask, float(np.max(pred)), bbox, True
