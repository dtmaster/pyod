# -*- coding: utf-8 -*-
"""Using Auto Encoder with Outlier Detection
"""
# Author: Yue Zhao <yuezhao@cs.toronto.edu>
# License: BSD 2 clause

from __future__ import division
from __future__ import print_function

import numpy as np
from keras.models import Sequential
from keras.layers import Dense, Dropout
from keras.regularizers import l2
from keras.losses import mean_squared_error
from sklearn.preprocessing import StandardScaler
from sklearn.utils import check_array
from sklearn.utils.validation import check_is_fitted

from ..utils.utility import check_parameter
from ..utils.stat_models import pairwise_distances_no_broadcast

from .base import BaseDetector


class AutoEncoder(BaseDetector):
    """
    Auto Encoder (AE) is a type of neural networks for learning useful data
    representations unsupervisedly. Similar to PCA, AE could be used to
    detect outlying objects in the data by calculating the reconstruction
    errors. See :cite:`aggarwal2015outlier` Chapter 3 for details.

    :param hidden_neurons: Number of neurons per hidden layers.

    :type hidden_neurons: list, optional (default=[64, 32, 32, 64])

    :param hidden_activation: Activation function to use for hidden layers.
        All hidden layers are forced to use the same type of activation.
        See https://keras.io/activations/
    :type hidden_activation: str, optional (default='relu')

    Warning: THIS IS

    :param output_activation:
    :type output_activation:

    :param loss: String (name of objective function) or objective function.
        See https://keras.io/losses/
    :type loss: str or obj, optional (default=keras.losses.mean_squared_error)

    :param optimizer: String (name of optimizer) or optimizer instance.
        See https://keras.io/optimizers/
    :type optimizer: str, optional (default='adam')

    :param epochs: Number of epochs to train the model.
    :type epochs: int, optional (default=100)

    :param batch_size: Number of samples per gradient update.
    :type batch_size: int, optional (default=32)

    :param dropout_rate:
    :type dropout_rate:

    :param l2_regularizer:
    :type l2_regularizer:

    :param validation_size:
    :type validation_size:

    :param preprocessing:
    :type preprocessing:

    :param verbose: Verbosity mode.

        - 0 = silent
        - 1 = progress bar
        - 2 = one line per epoch.
    :type verbose: int, optional (default=1)

    :param random_state: If int, random_state is the seed used by the random
        number generator; If RandomState instance, random_state is the random
        number generator; If None, the random number generator is the
        RandomState instance used by `np.random`.
    :type random_state: int, RandomState instance or None, optional
        (default=None)

    :param contamination: The amount of contamination of the data set, i.e.
        the proportion of outliers in the data set. When fitting this is used
        to define the threshold on the decision function.
    :type contamination: float in (0., 0.5), optional (default=0.1)

    :var bin_edges\_: The edges of the bins
    :vartype bin_edges\_: numpy array of shape (n_bins + 1, n_features )

    :var hist\_: The density of each histogram
    :vartype hist\_: numpy array of shape (n_bins, n_features)

    :var decision_scores\_: The outlier scores of the training data.
        The higher, the more abnormal. Outliers tend to have higher
        scores. This value is available once the detector is
        fitted.
    :vartype decision_scores\_: numpy array of shape (n_samples,)

    :var threshold\_: The threshold is based on ``contamination``. It is the
        ``n_samples * contamination`` most abnormal samples in
        ``decision_scores_``. The threshold is calculated for generating
        binary outlier labels.
    :vartype threshold\_: float

    :var labels\_: The binary labels of the training data. 0 stands for inliers
        and 1 for outliers/anomalies. It is generated by applying
        ``threshold_`` on ``decision_scores_``.
    :vartype labels\_: int, either 0 or 1
    """

    def __init__(self, hidden_neurons=[64, 32, 32, 64],
                 hidden_activation='relu', output_activation='sigmoid',
                 loss=mean_squared_error, optimizer='adam',
                 epochs=100, batch_size=32, dropout_rate=0.2,
                 l2_regularizer=0.1, validation_size=0.1, preprocessing=True,
                 verbose=1, random_state=None, contamination=0.1):
        super(AutoEncoder, self).__init__(contamination=contamination)
        self.hidden_neurons = hidden_neurons
        self.hidden_neurons_ = hidden_neurons
        self.hidden_activation = hidden_activation
        self.output_activation = output_activation
        self.loss = loss
        self.optimizer = optimizer
        self.epochs = epochs
        self.batch_size = batch_size
        self.dropout_rate = dropout_rate
        self.l2_regularizer = l2_regularizer
        self.validation_size = validation_size
        self.preprocessing = preprocessing
        self.verbose = verbose
        self.random_state = random_state

        # Verify the network design is valid
        if not self.hidden_neurons == self.hidden_neurons[::-1]:
            raise ValueError("Hidden units should be symmetric")

        check_parameter(dropout_rate, 0, 1, param_name='alpha')

    def _build_model(self):
        model = Sequential()
        # Input layer
        model.add(Dense(
            self.hidden_neurons_[0], activation=self.hidden_activation,
            input_shape=(self.n_features_,),
            activity_regularizer=l2(self.l2_regularizer)))
        model.add(Dropout(self.dropout_rate))

        # Additional layers
        for i in range(1, len(self.hidden_neurons_)):
            model.add(Dense(
                self.hidden_neurons_[i],
                activation=self.hidden_activation,
                activity_regularizer=l2(self.l2_regularizer)))
            model.add(Dropout(self.dropout_rate))

        # Output layers
        model.add(Dense(self.n_features_, activation=self.output_activation,
                        activity_regularizer=l2(self.l2_regularizer)))

        # Compile model
        model.compile(loss=self.loss, optimizer=self.optimizer)
        print(model.summary())
        return model

    def fit(self, X, y=None):
        # Validate inputs X and y (optional)
        X = check_array(X)
        self._set_n_classes(y)

        # Verify and construct the hidden units
        self.n_samples_, self.n_features_ = X.shape[0], X.shape[1]

        # Standardize data for better performance
        if self.preprocessing:
            self.scaler_ = StandardScaler()
            X_norm = self.scaler_.fit_transform(X)
        else:
            X_norm = np.copy(X)

        # Shuffle the data for validation as Keras do not shuffling for
        # Validation Split
        np.random.shuffle(X_norm)

        # Validate and complete the number of hidden neurons
        if np.min(self.hidden_neurons) > self.n_features_:
            raise ValueError("The number of neurons should not exceed "
                             "the number of features")
        self.hidden_neurons_.insert(0, self.n_features_)

        # Calculate the dimension of the encoding layer & compression rate
        self.encoding_dim_ = np.median(self.hidden_neurons)
        self.compression_rate_ = self.n_features_ // self.encoding_dim_

        # Build AE model & fit with X
        self.model_ = self._build_model()
        self.history_ = self.model_.fit(X_norm, X_norm,
                                        epochs=self.epochs,
                                        batch_size=self.batch_size,
                                        shuffle=True,
                                        validation_split=self.validation_size,
                                        verbose=self.verbose).history
        # Predict on X itself and calculate the reconstruction error as
        # the outlier scores. Noted X_norm was shuffled has to recreate
        if self.preprocessing:
            X_norm = self.scaler_.transform(X)
        else:
            X_norm = np.copy(X)

        pred_scores = self.model_.predict(X_norm)
        self.decision_scores_ = pairwise_distances_no_broadcast(X_norm,
                                                                pred_scores)
        self._process_decision_scores()
        return self

    def decision_function(self, X):
        check_is_fitted(self, ['model_', 'history_'])
        X = check_array(X)

        if self.preprocessing:
            X_norm = self.scaler_.transform(X)
        else:
            X_norm = np.copy(X)

        # Predict on X and return the reconstruction errors
        pred_scores = self.model_.predict(X_norm)
        return pairwise_distances_no_broadcast(X_norm, pred_scores)
