# -*- coding: utf-8 -*-
"""
This CNN model already gets ~85% validation accuracy without hyperparameter fine tuning.
Let's use Talos to max out the performance!
"""

# Commented out IPython magic to ensure Python compatibility.
# %tensorflow_version 1.x
import tensorflow as tf

import numpy as np
import pandas as pd
import talos
import W2V_Helpers.data_helpers as data_helpers
from W2V_Helpers.w2v import train_word2vec
from keras.models import Sequential, Model
from keras.layers import Dense, Dropout, Flatten, Input, MaxPooling1D, Convolution1D, Embedding
from keras.layers.merge import Concatenate
from keras.preprocessing import sequence
from sklearn.model_selection import KFold

np.random.seed(0)


# ---------------------- Parameters section -------------------
#
# Model type. See Kim Yoon's Convolutional Neural Networks for Sentence Classification, Section 3
model_type = "CNN-non-static"  # CNN-rand|CNN-non-static|CNN-static

# Data source
from pathlib import Path

data_path = str(Path(__file__).parent / "../Data")
train_data_path = data_path + "/mturk_train.csv"
train_data_x_col = "inputtext"
train_data_y_cols = ["rating1", "rating2", "rating3", "rating4", "rating5"]
#output_dir = "output"
#models_dir = "models"

# Model Hyperparameters
embedding_dim = 50
filter_sizes = (3, 8)
num_filters = 8
dropout_prob = (0.7, 0.9)
hidden_dims = 70

# Training parameters
batch_size = 64
num_epochs = 50

# Prepossessing parameters
sequence_length = 400
max_words = 5000

# Word2Vec parameters (see train_word2vec)
min_word_count = 1
context = 10

# ration of training dataset
train_percent = 0.9
#
# ---------------------- Parameters end -----------------------

def load_train_data(kfold = False):
    x, y, vocabulary, vocabulary_inv_list = data_helpers.load_train_data( train_path=train_data_path,
                                                                            train_x_col=train_data_x_col,
                                                                            train_y_cols=train_data_y_cols,
                                                                            save_path="W2V_Helpers"
                                                                            )
    vocabulary_inv = {key: value for key, value in enumerate(vocabulary_inv_list)}
    y = y.argmax(axis=1)

    if not kfold:
      # Shuffle data
      shuffle_indices = np.random.permutation(np.arange(len(y)))
      x = x[shuffle_indices]
      y = y[shuffle_indices]
      train_len = int(len(x) * train_percent)
      x_train = x[:train_len]
      y_train = y[:train_len]
      x_val = x[train_len:]
      y_val = y[train_len:]

      return x_train, y_train, x_val, y_val, vocabulary_inv
    else:
      #Create 10 folds for 10% training/validation
      train_ind_list = []
      test_ind_list = []
      kf = KFold(n_splits = 10)
      for train_ind, test_ind in kf.split(x):
        train_ind_list.append(train_ind)
        test_ind_list.append(test_ind)

      return x, y, train_ind_list, test_ind_list, vocabulary_inv


from keras.callbacks import EarlyStopping

def trainModel(x_train, x_val, vocabulary_inv, params):
  # Prepare embedding layer weights and convert inputs for static model
  print("Model type is", model_type)
  if model_type in ["CNN-non-static", "CNN-static"]:
      embedding_weights = train_word2vec(np.vstack((x_train, x_val)), vocabulary_inv, num_features=params['embedding_dim'],
                                        min_word_count=min_word_count, context=params['context'])
      if model_type == "CNN-static":
          x_train = np.stack([np.stack([embedding_weights[word] for word in sentence]) for sentence in x_train])
          x_val = np.stack([np.stack([embedding_weights[word] for word in sentence]) for sentence in x_val])
          print("x_train static shape:", x_train.shape)
          print("x_val static shape:", x_val.shape)

  elif model_type == "CNN-rand":
      embedding_weights = None
  else:
      raise ValueError("Unknown model type")


  # Build model
  if model_type == "CNN-static":
      input_shape = (params["sequence_length"], embedding_dim)
  else:
      input_shape = (params["sequence_length"],)

  model_input = Input(shape=input_shape)

  # Static model does not have embedding layer
  if model_type == "CNN-static":
      z = model_input
  else:
      z = Embedding(len(vocabulary_inv), params['embedding_dim'], input_length=params["sequence_length"], name="embedding")(model_input)

  z = Dropout(params['emb_drop'])(z)

  # Convolutional block
  conv_blocks = []
  for sz in params['filter_sizes']:
      conv = Convolution1D(filters=params['num_filters'],
                          kernel_size=sz,
                          padding="valid",
                          activation="relu",
                          strides=1)(z)
      conv = MaxPooling1D(pool_size=2)(conv)
      conv = Flatten()(conv)
      conv_blocks.append(conv)
  z = Concatenate()(conv_blocks) if len(conv_blocks) > 1 else conv_blocks[0]

  z = Dropout(params['hidden_drop'])(z)
  z = Dense(params['hidden_dims'], activation="relu")(z)
  model_output = Dense(1, activation="sigmoid")(z)

  model = Model(model_input, model_output)
  model.compile(loss="binary_crossentropy", optimizer="adam", metrics=["accuracy"])
  model.summary()

  # Initialize weights with word2vec
  if model_type == "CNN-non-static":
      weights = np.array([v for v in embedding_weights.values()])
      print("Initializing embedding layer with word2vec weights, shape", weights.shape)
      embedding_layer = model.get_layer("embedding")
      embedding_layer.set_weights([weights])

  early_stopping = EarlyStopping(min_delta = 0.01, mode = 'max', monitor='val_accuracy', patience = 4)
  callback = [early_stopping]
  history = model.fit(x_train, y_train, batch_size=params['batch_size'], epochs=num_epochs,
                    validation_data=(x_val, y_val), verbose=0)

  return history, model

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
path = str(Path(__file__).parent / "../Plots")

def plotHistory(history, i):
    epoch_count = range(1, len(history.history['loss']) + 1)
    plt.plot(epoch_count, history.history['loss'], 'r--')
    plt.plot(epoch_count, history.history['val_loss'], 'b-')
    plt.legend(['Training Loss', 'Validation Loss'])
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.savefig(path + "/w2v_cnn_loss_{}.png".format(i))
    plt.clf()

    plt.plot(history.history['accuracy'])
    plt.plot(history.history['val_accuracy'])
    plt.title('Model accuracy')
    plt.ylabel('Accuracy')
    plt.xlabel('Epoch')
    plt.legend(['Train', 'Validation'], loc='upper left')
    plt.savefig(path + "/w2v_cnn_accuracy_{}.png".format(i))

# Data Preparation
print("Load data...")

x_train, y_train, x_val, y_val, vocabulary_inv = load_train_data(False)

if sequence_length != x_val.shape[1]:
    print("Adjusting sequence length for actual size")
    sequence_length = x_val.shape[1]

print("x_train shape:", x_train.shape)
print("x_val shape:", x_val.shape)
print("Vocabulary Size: {:d}".format(len(vocabulary_inv)))

#Set search parameters
p = {'embedding_dim':[20, 50, 100],
    'context': [5, 10, 15],
    'sequence_length':[sequence_length],
    'filter_sizes':[(3,8),(2,3,8)],
    'num_filters':[8,10,30,100],
    'emb_drop':[0.5, 0.7, 0.9],
    'hidden_drop':[0.7, 0.9, 0.95],
    'hidden_dims':[70, 140],
    'batch_size':[64, 128],
    }

#Run search
scan_object = talos.Scan(x_train, y_train, x_val = x_val, y_val = y_val,
                        val_split = None, params = p, model = trainModel,
                        experiment_name = "w2v_cnn_optimize")

#Get best parameters
r = talos.Reporting(scan_object)
print(r.best_params())

#history, model = trainModel(x_train, x_val, vocabulary_inv)

'''plotHistory(history, 0)
score = model.evaluate(x_val, y_val, batch_size=32, verbose=1)
print('Test loss:', score[0])
print('Test accuracy:', score[1])'''

#x_train, y_train, x_val, y_val, vocabulary_inv = load_train_data()
'''x, y, train_ind_list, test_ind_list, vocabulary_inv = load_train_data(True)

loss_list = []
accuracy_list = []
for i in range(len(train_ind_list)):
  print("Training on kfold {}...".format(i+1))
  x_train = x[train_ind_list[i]]
  x_val = x[test_ind_list[i]]
  y_train = y[train_ind_list[i]]
  y_val = y[test_ind_list[i]]

  if sequence_length != x_val.shape[1]:
      print("Adjusting sequence length for actual size")
      sequence_length = x_val.shape[1]

  print("x_train shape:", x_train.shape)
  print("x_val shape:", x_val.shape)
  print("Vocabulary Size: {:d}".format(len(vocabulary_inv)))

  model = loadModel(x_train, x_val, vocabulary_inv)

  # Train the model
  from keras.callbacks import EarlyStopping
  early_stopping = EarlyStopping(min_delta = 0.01, mode = 'max', monitor='val_acc', patience = 2)
  callback = [early_stopping]
  history = model.fit(x_train, y_train, batch_size=batch_size, epochs=num_epochs,
                      validation_data=(x_val, y_val), verbose=1)
  plotHistory(history, i)
  score = model.evaluate(x_val, y_val, batch_size=32, verbose=1)
  print('Test loss:', score[0])
  print('Test accuracy:', score[1])
  loss_list.append(score[0])
  accuracy_list.append(score[1])

print("Average 10-fold validation loss: {}".format(sum(loss_list)/len(loss_list)))
print("Average 10-fold validation accuracy: {}".format(sum(accuracy_list)/len(accuracy_list)))
'''

# Create count of the number of epochs
# Visualize learning curve. Here learning curve is not ideal. It should be much smoother as it decreases.
#As mentioned before, altering different hyper parameters especially learning rate can have a positive impact
#on accuracy and learning curve.

#
# **If validation loss >> training loss you can call it overfitting.**
#
# If validation loss  > training loss you can call it some overfitting.
#
# If validation loss  < training loss you can call it some underfitting.
#
# If validation loss << training loss you can call it underfitting.
#
# Just right if training loss ~ validation loss
#
# -----------------------------------------
#
# ### Steps for reducing overfitting:
#
# 1. Add more data
# 2. Use data augmentation
# 3. Use architectures that generalize well
# 4. Add regularization (mostly dropout, L1/L2 regularization are also possible)
# 5. Reduce architecture complexity.
#

# print test accuracy
'''score = model.evaluate(x_val, y_val, batch_size=32, verbose=1)
print('Test loss:', score[0])
print('Test accuracy:', score[1])'''

#data_helpers.save_model(model, models_dir)
