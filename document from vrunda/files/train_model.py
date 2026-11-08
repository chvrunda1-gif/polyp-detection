import hashlib
import os
from pathlib import Path

import numpy as np
import tensorflow as tf
from tensorflow.keras import layers, models

IMG_SIZE = 224
BATCH_SIZE = 8
EPOCHS = int(os.environ.get("TRAIN_EPOCHS", "20"))
SEED = 42
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MODEL_PATH = Path("models/polyp_segmenter.keras")


def list_images(folder):
    return sorted(
        path for path in Path(folder).iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as image_file:
        for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pair_polyp_images(split, source_images, source_masks):
    pairs = []
    for image_path in list_images(Path("data/polyp") / split):
        source_path = source_images.get(file_sha256(image_path))
        if source_path is None:
            raise RuntimeError(f"Could not match {image_path} to a source Kvasir image")
        mask_path = source_masks / source_path.name
        if not mask_path.is_file():
            raise RuntimeError(f"Missing segmentation mask for {source_path.name}")
        pairs.append((image_path, mask_path))
    return pairs


def split_paths(paths, validation_ratio=0.2):
    shuffled = list(paths)
    np.random.default_rng(SEED).shuffle(shuffled)
    split_at = int(len(shuffled) * (1 - validation_ratio))
    return shuffled[:split_at], shuffled[split_at:]


def build_dataset(pairs, training):
    image_paths = [str(image) for image, _ in pairs]
    mask_paths = [str(mask) if mask else "" for _, mask in pairs]
    ds = tf.data.Dataset.from_tensor_slices((image_paths, mask_paths))

    def load_pair(image_path, mask_path):
        image = tf.io.decode_image(
            tf.io.read_file(image_path), channels=3, expand_animations=False
        )
        image = tf.image.resize(image, [IMG_SIZE, IMG_SIZE])
        image = tf.cast(image, tf.float32) / 255.0
        image.set_shape([IMG_SIZE, IMG_SIZE, 3])

        def load_mask():
            mask = tf.io.decode_image(
                tf.io.read_file(mask_path), channels=1, expand_animations=False
            )
            mask = tf.image.resize(mask, [IMG_SIZE, IMG_SIZE], method="nearest")
            return tf.cast(mask > 127, tf.float32)

        mask = tf.cond(
            tf.strings.length(mask_path) > 0,
            load_mask,
            lambda: tf.zeros([IMG_SIZE, IMG_SIZE, 1], dtype=tf.float32),
        )
        mask.set_shape([IMG_SIZE, IMG_SIZE, 1])

        if training:
            if tf.random.uniform(()) > 0.5:
                image = tf.image.flip_left_right(image)
                mask = tf.image.flip_left_right(mask)
            if tf.random.uniform(()) > 0.5:
                image = tf.image.flip_up_down(image)
                mask = tf.image.flip_up_down(mask)
            image = tf.image.random_brightness(image, max_delta=0.08)
            image = tf.clip_by_value(image, 0.0, 1.0)

        return image, mask

    ds = ds.map(load_pair, num_parallel_calls=tf.data.AUTOTUNE)
    if training:
        ds = ds.shuffle(len(pairs), seed=SEED, reshuffle_each_iteration=True)
    return ds.batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)


def dice_loss(y_true, y_pred):
    axes = [1, 2, 3]
    intersection = tf.reduce_sum(y_true * y_pred, axis=axes)
    denominator = tf.reduce_sum(y_true + y_pred, axis=axes)
    dice = (2.0 * intersection + 1.0) / (denominator + 1.0)
    return 1.0 - tf.reduce_mean(dice)


def segmentation_loss(y_true, y_pred):
    binary_crossentropy = tf.keras.losses.binary_crossentropy(y_true, y_pred)
    return tf.reduce_mean(binary_crossentropy) + dice_loss(y_true, y_pred)


def build_model():
    inputs = layers.Input((IMG_SIZE, IMG_SIZE, 3))
    skips = []
    x = inputs

    for filters in (32, 64, 128, 256):
        x = layers.Conv2D(filters, 3, padding="same", activation="relu")(x)
        x = layers.Conv2D(filters, 3, padding="same", activation="relu")(x)
        skips.append(x)
        x = layers.MaxPooling2D(2)(x)

    x = layers.Conv2D(512, 3, padding="same", activation="relu")(x)
    x = layers.Conv2D(512, 3, padding="same", activation="relu")(x)

    for filters, skip in zip((256, 128, 64, 32), reversed(skips)):
        x = layers.UpSampling2D(2, interpolation="bilinear")(x)
        x = layers.Concatenate()([x, skip])
        x = layers.Conv2D(filters, 3, padding="same", activation="relu")(x)
        x = layers.Conv2D(filters, 3, padding="same", activation="relu")(x)

    outputs = layers.Conv2D(1, 1, activation="sigmoid", name="polyp_mask")(x)
    model = models.Model(inputs, outputs, name="polyp_unet")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),
        loss=segmentation_loss,
        metrics=[tf.keras.metrics.BinaryIoU(target_class_ids=[1], threshold=0.5, name="polyp_iou")],
    )
    return model


def main():
    source_image_dir = Path("Kvasir-seg/images")
    source_mask_dir = Path("Kvasir-seg/masks")
    if not source_image_dir.is_dir() or not source_mask_dir.is_dir():
        raise RuntimeError("Kvasir-seg/images and Kvasir-seg/masks are required")

    source_images = {
        file_sha256(path): path for path in list_images(source_image_dir)
    }
    positive_train = pair_polyp_images("train", source_images, source_mask_dir)
    positive_val = pair_polyp_images("val", source_images, source_mask_dir)
    normal_images = list_images("data/no_polyp")
    if not positive_train or not positive_val:
        raise RuntimeError("Polyp training and validation images are required")
    if len(normal_images) < 10:
        raise RuntimeError("At least 10 normal images are required")

    normal_train, normal_val = split_paths(normal_images)
    train_pairs = positive_train + [(image, None) for image in normal_train]
    val_pairs = positive_val + [(image, None) for image in normal_val]

    print(f"Train samples: {len(train_pairs)} (polyp={len(positive_train)}, normal={len(normal_train)})")
    print(f"Validation samples: {len(val_pairs)} (polyp={len(positive_val)}, normal={len(normal_val)})")

    model = build_model()
    model.summary()
    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=4, restore_best_weights=True
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss", factor=0.5, patience=2, min_lr=1e-6
        ),
    ]
    model.fit(
        build_dataset(train_pairs, training=True),
        validation_data=build_dataset(val_pairs, training=False),
        epochs=EPOCHS,
        callbacks=callbacks,
        shuffle=False,
    )

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save(MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")
    print("This research model is not clinically validated.")


if __name__ == "__main__":
    main()