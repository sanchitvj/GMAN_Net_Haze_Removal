#  ====================================================
#   Filename: dehazenet_input.py
#   Function: This file is used to read Clear and hazed images.
#   In the program, we read images and put them into related
#   Arrays.
#  ====================================================

import tensorflow as tf
import numpy as np

import os
import sys

from Image import *
import dehazenet as dehazenet


IMAGE_INDEX_BIT = 4
NUM_EXAMPLES_PER_EPOCH_FOR_TRAIN = 50000
NUM_EXAMPLES_PER_EPOCH_FOR_EVAL = 10000


def image_list_shuffle(image_list):
    np.random.shuffle(image_list)
    return image_list


def image_input(dir, file_names, image_list, clear_dict, clear_image):
    """
        :param dir: The directory to read the image
        :param file_names: An empty list to save all image file names
        :return: A list used to save all Image objects.A list used to save names
    """
    if not dir:
        raise ValueError('Please supply a data_dir')
    file_list = os.listdir(dir)
    for image_filename in file_list:
        if os.path.isdir(os.path.join(dir, image_filename)):
            image_input(os.path.join(dir, image_filename), file_names, image_list, clear_dict, clear_image)
        elif image_filename.endswith(".png") \
                | image_filename.endswith(".jpg"):
            file_name = os.path.join(dir, image_filename)
            file_names.append(file_name)
            current_image = Image(path=file_name)
            current_image.key = id(current_image)
            current_image.image_index = image_filename[0:IMAGE_INDEX_BIT]
            image_list.append(current_image)
            # Put all clear images into dictionary
            if clear_image:
                if len(image_filename) < IMAGE_INDEX_BIT + 4:
                    raise RuntimeError("Incorrect image name: " + image_filename)
                clear_dict[current_image.image_index] = current_image
    return file_names, image_list, clear_dict


def _read_image(image_list, file_names=None):
    """
    :param image_list: A image list which saves the image objects
    :param file_names: A file name list(Optional)
    :return: A image list whose image_matrix is filled
    """
    for image in image_list:
        image_content = tf.read_file(image.path)
        if image.path.endswith(".png"):
            image_matrix = tf.image.decode_png(image_content,
                                               channels=dehazenet.RGB_CHANNEL, dtype=tf.uint8)
        elif image.path.endswith("jpg"):
            image_matrix = tf.image.decode_jpeg(image_content, channels=dehazenet.RGB_CHANNEL)
        # TODO Need to be modified
        # image_matrix = tf.cast(image_matrix, tf.float32)
        # rshape = tf.reshape(tf.reduce_mean(image_matrix, [0, 1]), [1, 1, 3])
        # image_matrix = image_matrix / rshape * 128
        image.image_matrix = image_matrix
    return image_list


def _generate_image_batch(hazed_image, clear_image, min_queue_examples, batch_size, shuffle=True):
    num_preprocess_threads = 16

    if shuffle:
        h_images, c_images = tf.train.shuffle_batch(
            [hazed_image, clear_image],
            batch_size=batch_size,
            num_threads=num_preprocess_threads,
            capacity=min_queue_examples + 3 * batch_size,
            min_after_dequeue=min_queue_examples)
    else:
        h_images, c_images = tf.train.batch(
            [hazed_image, clear_image],
            batch_size=batch_size,
            num_threads=num_preprocess_threads,
            capacity=min_queue_examples + 3 * batch_size)

    # Display the training images in the visualizer.
    tf.summary.image('hazed_images', h_images)
    tf.summary.image('clear_images', c_images)
    return h_images,c_images


def _image_pre_process(image, height, width):
    image = tf.cast(image, tf.float32)
    image = tf.image.random_brightness(image, max_delta=63)
    image = tf.image.random_contrast(image, lower=0.2, upper=1.8)
    # Subtract off the mean and divide by the variance of the pixels.
    image = tf.image.per_image_standardization(image)
    # Resize the input image
    image.set_shape([height, width, 3])
    return image


def _find_corres_clear_image(image, clear_dict):
    clear_image_obj = clear_dict[image.image_index]
    image_content = tf.read_file(clear_image_obj.path)
    if clear_image_obj.path.endswith(".png"):
        image_matrix = tf.image.decode_png(image_content,
                                           channels=dehazenet.RGB_CHANNEL, dtype=tf.uint8)
    elif clear_image_obj.path.endswith("jpg"):
        image_matrix = tf.image.decode_jpeg(image_content, channels=dehazenet.RGB_CHANNEL)
    return image_matrix


def get_distorted_image(image_batch_list, height, width, file_names=None):
    """
    :param batch_list: A list used to save a batch of image objects
    :param height: The height of our training image
    :param width: The width of our training image
    :param file_names: A batch of images to be trained(Optional)
    :return: A batch list of Image object whose image_matrix are filled
    :function: Used to read and distort a batch of images
    """
    if isinstance(height, int) | isinstance(width, int) \
            | image_batch_list is not None:
        for image in image_batch_list:
            if not tf.gfile.Exists(image.path):
                raise ValueError('Failed to find image: ' + image.path)
        original_image_batch = []
        original_image_batch = _read_image(image_batch_list)
        # TODO Must be modified
        for image in original_image_batch:
            if image.image_matrix is None:
                raise RuntimeError("Failed to read image: " + image.path)
            # Random crop is not suitable for DeHazeNet
            # image.image_matrix = tf.random_crop(
            #     image.image_matrix, [height, width, dehazenet.RGB_CHANNEL])
            image.image_matrix = _image_pre_process(image.image_matrix, height, width)
            min_fraction_of_examples_in_queue = 0.4
            min_queue_examples = int(NUM_EXAMPLES_PER_EPOCH_FOR_TRAIN *
                                     min_fraction_of_examples_in_queue)
            clear_image = _find_corres_clear_image(image)
            print('Filling queue with %d images before starting to train. '
                  'This will take a few minutes.' % min_queue_examples)
        return _generate_image_batch(image.image_matrix, clear_image, min_queue_examples, dehazenet.FLAGS.batch_size,
                                     shuffle=True)
    else:
        raise RuntimeError('Error input of method distorted_image')


def _get_image_batch(epoch_index, batch_index, batch_size, hazed_input_img_list, clear_dict):
    image_input_batch = []
    image_truthground_batch = []
    image_truthground_list = []
    index = (epoch_index - 1) * (batch_index - 1) * batch_size
    image_batch_list = hazed_input_img_list[index:index+batch_size]
    image_input_obj_batch = get_distorted_image(image_batch_list, dehazenet.FLAGS.input_image_height,
                                            dehazenet.FLAGS.input_image_width)
    for img in image_input_obj_batch:
        image_input_batch.append(img.image_matrix)
    for image in image_input_obj_batch:
            # Find corresponding clear image object and add them into image_truthground_list
        clear_image = clear_dict[image.image_index]
        image_truthground_list.append(clear_image)
    image_truthground_obj_batch = get_distorted_image(image_truthground_list, dehazenet.FLAGS.input_image_height,
                                                  dehazenet.FLAGS.input_image_width)
    for img in image_truthground_obj_batch:
        image_truthground_batch.append(img.image_matrix)
    return image_input_batch, image_truthground_batch


if __name__ == '__main__':
    # Unit test
    file_names = []
    image_list=[]
    clear_dict = {}
    image_input("./ClearImages", file_names, image_list, clear_dict=clear_dict,clear_image=True)
    image_list_shuffle(image_list)
    print(file_names)
    print(image_list)
    print(clear_dict)
    image_list = _read_image(image_list)
    for img in image_list:
        print(tf.size(img.image_matrix))
    a = [1,2,3]
    print(tf.size(a))
    print(np.shape(a))
    # get_image_batch(1, 2, image_list, clear_dict)