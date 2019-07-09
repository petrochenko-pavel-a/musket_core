from musket_core import datasets

import numpy as np

import keras

import tensorflow as tf

import lightgbm

import os

class OutputMeta:
    def __init__(self, shape, owner):
        self.output_meta = True
        self.model = owner

class Log():
    def __init__(self):
        pass

    def get(self, monitor):
        pass

class RGetter:
    def get(self, key):
        return self.__dict__[key]

    def __getitem__(self, item):
        if not item in self.__dict__.keys():
            print("KEY: " + str(item))

        return self.__dict__[item]

    def keys(self):
        return self.__dict__.keys()

    def has_key(self, k):
        return k in self.__dict__

    def values(self):
        return self.__dict__.values()

    def items(self):
        return self.__dict__.items()

    def __cmp__(self, dict_):
        return self.__cmp__(self.__dict__, dict_)

    def __contains__(self, item):
        return item in self.__dict__

    def __iter__(self):
        return iter(self.__dict__)

    def __unicode__(self):
        return unicode(repr(self.__dict__))

class GradientBoosting:
    def __init__(self, output_dim, boosting_type='gbdt', num_leaves=31, max_depth=-1, learning_rate=0.1, n_estimators=100, subsample_for_bin=200000, class_weight=None, min_split_gain=0., min_child_weight=1e-3, min_child_samples=20, subsample=1., subsample_freq=0, colsample_bytree=1., reg_alpha=0., reg_lambda=0., random_state=None, n_jobs=-1, silent=True, importance_type='split'):
        if output_dim > 1:
            objective = "multiclass"
        else:
            objective = "regression"

        self.model = lightgbm.LGBMModel(boosting_type, num_leaves, max_depth, learning_rate, n_estimators, subsample_for_bin, objective, class_weight, min_split_gain, min_child_weight, min_child_samples, subsample, subsample_freq, colsample_bytree, reg_alpha, reg_lambda, random_state, n_jobs, silent, importance_type, n_classes=output_dim, first_metric_only=True)

        self.output_dim = output_dim

        self.custom_metrics = {}

        self.result = None

        self.rgetter = RGetter()

        self.stop_training = False

    def __call__(self, *args, **kwargs):
        return OutputMeta(self.output_dim, self)

    def compile(self, *args, **kwargs):
        for item in args[2]:
            self.custom_metrics[item] = self.to_tensor(keras.metrics.get(item))

    def eval_metrics(self, y_true, y_pred, session):
        result = {}

        for item in self.custom_metrics.keys():
            func = self.custom_metrics[item][0]

            arg1 = self.custom_metrics[item][1]
            arg2 = self.custom_metrics[item][2]

            result[item] = session.run(func, {arg1: y_true, arg2: y_pred})

        return result

    def to_tensor(self, func):
        i1 = keras.layers.Input((self.output_dim,))
        i2 = keras.layers.Input((self.output_dim,))

        return func(i1, i2), i1, i2

    def convert_data(self, generator):
        result_x = []
        result_y = []

        for item in generator:
            result_x.append(item[0])
            result_y.append(item[1])

        result_x = np.concatenate(result_x)
        result_y = np.concatenate(result_y)

        result_x = np.reshape(result_x, (len(result_x), -1))
        result_y = np.reshape(result_y, (len(result_y), -1))

        if self.output_dim > 1:
            result_y = np.argmax(result_y, 1)

        return result_x.astype(np.float32), result_y.astype(np.int32)

    def predict(self, *args, **kwargs):
        input = np.array(args)[0]

        input = np.reshape(input, (len(input), -1))

        self.model._n_features = input.shape[1]

        predictions = self.model.predict(input)

        return predictions

    def load_weights(self, path, val):
        if os.path.exists(path):
            self.model._Booster = lightgbm.Booster(model_file=path)

    def numbers_to_vectors(self, numbers):
        result = np.zeros((len(numbers), self.output_dim))

        count = 0

        for item in numbers:
            result[count, item] = 1

            count += 1

        return result

    def groups_to_vectors(self, data, length):
        result = np.zeros((length, self.output_dim))

        for item in range(self.output_dim):
            result[:, item] = data[length * item : length * (item + 1)]

        return result

    def to_tf(self, numbers, data):
        y_true = self.numbers_to_vectors(numbers)

        y_pred = self.groups_to_vectors(data, len(numbers))

        return y_true, y_pred

    def save(self, file_path, overwrite):
        if hasattr(self.model, "booster_"):
            self.model.booster_.save_model(file_path)

    def fit_generator(self, *args, **kwargs):
        callbacks = kwargs["callbacks"]

        file_path = None
        early_stopping_rounds = None

        for item in callbacks:
            if hasattr(item, "filepath"):
                file_path = item.filepath

        generator_train = args[0]
        generator_test = kwargs["validation_data"]

        train_x, train_y = self.convert_data(generator_train)
        val_x, val_y = self.convert_data(generator_test)

        self.model.n_estimators = kwargs["epochs"]

        checkpoint_cb = None

        for item in callbacks:
            item.set_model(self)
            item.on_train_begin()

            if "ModelCheckpoint" in str(item):
                checkpoint_cb = item

        def custom_metric(y_true, y_pred):
            true, pred = self.to_tf(y_true, y_pred)

            results = self.eval_metrics(true, pred, tf.get_default_session())

            for item in list(results.keys()):
                results["val_" + item] = np.mean(results[item])

            self.rgetter.__dict__ = results

            return checkpoint_cb.monitor, np.mean(results[checkpoint_cb.monitor]), "great" in str(checkpoint_cb.monitor_op)

        def custom_callback(*args, **kwargs):
            iter = args[0][2]

            for item in callbacks:
                if "ReduceLROnPlateau" in str(item):
                    continue

                item.on_epoch_end(iter, self.rgetter)

        self.model.fit(train_x, train_y, eval_set=[(val_x, val_y)], callbacks = [custom_callback], eval_metric = custom_metric)

        # for item in callbacks:
        #     if "ReduceLROnPlateau" in str(callbacks):
        #         continue
        #
        #     item.on_epoch_end(0, self.rgetter)

        for item in callbacks:
            item.on_train_end()

        #self.model.booster_.save_model(file_path)