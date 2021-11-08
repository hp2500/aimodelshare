# data wrangling
import pandas as pd
import numpy as np

# ml frameworks
import sklearn
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV
import torch
import xgboost
import tensorflow as tf

# onnx modules
import onnx
import skl2onnx
from skl2onnx import convert_sklearn
import tf2onnx
from torch.onnx import export
from onnx.tools.net_drawer import GetPydotGraph, GetOpNodeProducer
import importlib
import onnxmltools
import onnxruntime as rt


# aims modules
from aimodelshare.aws import run_function_on_lambda, get_aws_client
from aimodelshare.determinism import set_determinism_env

# os etc
import os
import ast
import tempfile
import json
import re
import pickle
import requests
import sys
import tempfile
import wget            


from pympler import asizeof
from IPython.core.display import display, HTML, SVG
import absl.logging
import networkx as nx

absl.logging.set_verbosity(absl.logging.ERROR)

def _extract_onnx_metadata(onnx_model, framework):
    '''Extracts model metadata from ONNX file.'''

    # get model graph
    graph = onnx_model.graph

    # initialize metadata dict
    metadata_onnx = {}

    # get input shape
    metadata_onnx["input_shape"] = graph.input[0].type.tensor_type.shape.dim[1].dim_value

    # get output shape
    metadata_onnx["output_shape"] = graph.output[0].type.tensor_type.shape.dim[1].dim_value 
    
    # get layers and activations NEW
    # match layers and nodes and initalizers in sinle object
    # insert here....

    # get layers & activations 
    layer_nodes = ['MatMul', 'Gemm', 'Conv'] #add MaxPool, Transpose, Flatten
    activation_nodes = ['Relu', 'Softmax']

    layers = []
    activations = []

    for op_id, op in enumerate(graph.node):

        if op.op_type in layer_nodes:
            layers.append(op.op_type)
            #if op.op_type == 'MaxPool':
                #activations.append(None)
            
        if op.op_type in activation_nodes:
            activations.append(op.op_type)


    # get shapes and parameters
    layers_shapes = []
    layers_n_params = []

    if framework == 'keras':
        initializer = list(reversed(graph.initializer))
        for layer_id, layer in enumerate(initializer):
            if(len(layer.dims)>= 2):
                layers_shapes.append(layer.dims[1])

                try:
                    n_params = int(np.prod(layer.dims) + initializer[layer_id-1].dims)
                except:
                    n_params = None

                layers_n_params.append(n_params)
                

    elif framework == 'pytorch':
        initializer = graph.initializer
        for layer_id, layer in enumerate(initializer):
            if(len(layer.dims)>= 2):
                layers_shapes.append(layer.dims[0])
                n_params = int(np.prod(layer.dims) + initializer[layer_id-1].dims)
                layers_n_params.append(n_params)


    # get model architecture stats
    model_architecture = {'layers_number': len(layers),
                      'layers_sequence': layers,
                      'layers_summary': {i:layers.count(i) for i in set(layers)},
                      'layers_n_params': layers_n_params,
                      'layers_shapes': layers_shapes,
                      'activations_sequence': activations,
                      'activations_summary': {i:activations.count(i) for i in set(activations)}
                     }

    metadata_onnx["model_architecture"] = model_architecture

    return metadata_onnx



def _misc_to_onnx(model, initial_types, transfer_learning=None,
                    deep_learning=None, task_type=None):

    # generate metadata dict 
    metadata = {}
    
    # placeholders, need to be generated elsewhere
    metadata['model_id'] = None
    metadata['data_id'] = None
    metadata['preprocessor_id'] = None
    
    # infer ml framework from function call
    if isinstance(model, (xgboost.XGBClassifier, xgboost.XGBRegressor)):
        metadata['ml_framework'] = 'xgboost'
        onx = onnxmltools.convert.convert_xgboost(model, initial_types=initial_types)

    # also integrate lightGBM 
    
    # get model type from model object
    model_type = str(model).split('(')[0]
    metadata['model_type'] = model_type
    
    # get transfer learning bool from user input
    metadata['transfer_learning'] = transfer_learning

    # get deep learning bool from user input
    metadata['deep_learning'] = deep_learning
    
    # get task type from user input
    metadata['task_type'] = task_type
    
    # placeholders, need to be inferred from data 
    metadata['target_distribution'] = None
    metadata['input_type'] = None
    metadata['input_shape'] = None
    metadata['input_dtypes'] = None       
    metadata['input_distribution'] = None
    
    # get model config dict from sklearn model object
    metadata['model_config'] = str(model.get_params())

    # get model state from sklearn model object
    metadata['model_state'] = None


    model_architecture = {}

    if hasattr(model, 'coef_'):
        model_architecture['layers_n_params'] = [len(model.coef_.flatten())]
    if hasattr(model, 'solver'):
        model_architecture['optimizer'] = model.solver

    metadata['model_architecture'] = str(model_architecture)

    metadata['memory_size'] = asizeof.asizeof(model)    


    # placeholder, needs evaluation engine
    metadata['eval_metrics'] = None  
    
    # add metadata from onnx object
    # metadata['metadata_onnx'] = str(_extract_onnx_metadata(onx, framework='sklearn'))
    metadata['metadata_onnx'] = None

    meta = onx.metadata_props.add()
    meta.key = 'model_metadata'
    meta.value = str(metadata)

    return onx



def _sklearn_to_onnx(model, initial_types, transfer_learning=None,
                    deep_learning=None, task_type=None):
    '''Extracts metadata from sklearn model object.'''
    
    # check whether this is a fitted sklearn model
    # sklearn.utils.validation.check_is_fitted(model)

    # deal with pipelines and parameter search 
    if isinstance(model, (GridSearchCV, RandomizedSearchCV)):
        model = model.best_estimator_

    if isinstance(model, sklearn.pipeline.Pipeline):
        model = model.steps[-1][1]

    # fix ensemble voting models
    if all([hasattr(model, 'flatten_transform'),hasattr(model, 'voting')]):
      model.flatten_transform=False
    
    # convert to onnx
    onx = convert_sklearn(model, initial_types=initial_types)
    
    ## Dynamically set model ir_version to ensure sklearn opsets work properly
    from onnx.helper import VERSION_TABLE
    import onnx
    import numpy as np

    indexlocationlist=[]
    for i in VERSION_TABLE:
      indexlocationlist.append(str(i).find(str(onnx.__version__)))


    arr = np.array(indexlocationlist)

    def condition(x): return x > -1

    bool_arr = condition(arr)

    output = np.where(bool_arr)[0]

    ir_version=VERSION_TABLE[output[0]][1]

    #add to model object before saving
    onx.ir_version = ir_version
    
    # generate metadata dict 
    metadata = {}
    
    # placeholders, need to be generated elsewhere
    metadata['model_id'] = None
    metadata['data_id'] = None
    metadata['preprocessor_id'] = None
    
    # infer ml framework from function call
    metadata['ml_framework'] = 'sklearn'
    
    # get model type from model object
    model_type = str(model).split('(')[0]
    metadata['model_type'] = model_type
    
    # get transfer learning bool from user input
    metadata['transfer_learning'] = transfer_learning

    # get deep learning bool from user input
    metadata['deep_learning'] = deep_learning
    
    # get task type from user input
    metadata['task_type'] = task_type
    
    # placeholders, need to be inferred from data 
    metadata['target_distribution'] = None
    metadata['input_type'] = None
    metadata['input_shape'] = None
    metadata['input_dtypes'] = None       
    metadata['input_distribution'] = None
    
    # get model config dict from sklearn model object
    metadata['model_config'] = str(model.get_params())

    # get weights for pretrained models 
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, 'temp_file_name')

    with open(temp_path, 'wb') as f:
        pickle.dump(model, f)

    with open(temp_path, "rb") as f:
        pkl_str = f.read()

    metadata['model_weights'] = pkl_str
    
    # get model state from sklearn model object
    metadata['model_state'] = None

    # get model architecture    
    if model_type == 'MLPClassifier' or model_type == 'MLPRegressor':

        if model_type == 'MLPClassifier':
            loss = 'log-loss'
        if model_type == 'MLPRegressor':
            loss = 'squared-loss'

        n_params = []
        layer_dims = [model.n_features_in_] + model.hidden_layer_sizes + [model.n_outputs_]
        for i in range(len(layer_dims)-1):
            n_params.append(layer_dims[i]*layer_dims[i+1] + layer_dims[i+1])

        # insert data into model architecture dict 
        model_architecture = {'layers_number': len(model.hidden_layer_sizes),
                              'layers_sequence': ['Dense']*len(model.hidden_layer_sizes),
                              'layers_summary': {'Dense': len(model.hidden_layer_sizes)},
                              'layers_n_params': n_params, #double check 
                              'layers_shapes': model.hidden_layer_sizes,
                              'activations_sequence': [model.activation]*len(model.hidden_layer_sizes),
                              'activations_summary': {model.activation: len(model.hidden_layer_sizes)},
                              'loss': loss,
                              'optimizer': model.solver
                             }

        metadata['model_architecture'] = str(model_architecture)


    else:
        model_architecture = {}

        if hasattr(model, 'coef_'):
            model_architecture['layers_n_params'] = [len(model.coef_.flatten())]
        if hasattr(model, 'solver'):
            model_architecture['optimizer'] = model.solver

        metadata['model_architecture'] = str(model_architecture)

    metadata['memory_size'] = asizeof.asizeof(model)    

    # placeholder, needs evaluation engine
    metadata['eval_metrics'] = None  
    
    # add metadata from onnx object
    # metadata['metadata_onnx'] = str(_extract_onnx_metadata(onx, framework='sklearn'))
    metadata['metadata_onnx'] = None

    meta = onx.metadata_props.add()
    meta.key = 'model_metadata'
    meta.value = str(metadata)

    return onx



def _keras_to_onnx(model, transfer_learning=None,
                  deep_learning=None, task_type=None, epochs=None):
    '''Extracts metadata from keras model object.'''

    # check whether this is a fitted keras model
    # isinstance...


    # handle keras models in sklearn wrapper
    if isinstance(model, (GridSearchCV, RandomizedSearchCV)):
        model = model.best_estimator_

    if isinstance(model, sklearn.pipeline.Pipeline):
        model = model.steps[-1][1]

    sklearn_wrappers = (tf.keras.wrappers.scikit_learn.KerasClassifier,
                    tf.keras.wrappers.scikit_learn.KerasRegressor)

    if isinstance(model, sklearn_wrappers):
        model = model.model
    
    # convert to onnx
    #onx = convert_keras(model)
    # generate tempfile for onnx object 
    temp_dir = os.path.join(tempfile.gettempdir(), 'test')
    temp_dir = tempfile.gettempdir()



    
    tf.get_logger().setLevel('ERROR') # probably not good practice
    output_path = os.path.join(temp_dir, 'temp.onnx')

    model.save(temp_dir)

    # Convert the model
    converter = tf.lite.TFLiteConverter.from_saved_model(temp_dir) # path to the SavedModel directory
    tflite_model = converter.convert()

    # Save the model.
    with open(os.path.join(temp_dir,'tempmodel.tflite'), 'wb') as f:
      f.write(tflite_model)

    modelstringtest="python -m tf2onnx.convert --tflite "+os.path.join(temp_dir,'tempmodel.tflite')+" --output "+output_path+" --opset 13"
    os.system(modelstringtest)
    output_path = os.path.join(temp_dir, 'temp.onnx')
    modelstringtest="python -m tf2onnx.convert --saved-model "+temp_dir+" --output "+output_path+" --opset 13"
    os.system(modelstringtest)
    onx = onnx.load(output_path)


    # generate metadata dict 
    metadata = {}

    # placeholders, need to be generated elsewhere
    metadata['model_id'] = None
    metadata['data_id'] = None
    metadata['preprocessor_id'] = None

    # infer ml framework from function call
    metadata['ml_framework'] = 'keras'

    # get model type from model object
    metadata['model_type'] =  str(model.__class__.__name__)

    # get transfer learning bool from user input
    metadata['transfer_learning'] = transfer_learning

    # get deep learning bool from user input
    metadata['deep_learning'] = deep_learning

    # get task type from user input
    metadata['task_type'] = task_type

    # placeholders, need to be inferred from data 
    metadata['target_distribution'] = None
    metadata['input_type'] = None
    metadata['input_shape'] = None
    metadata['input_dtypes'] = None       
    metadata['input_distribution'] = None

    # get model config dict from keras model object
    metadata['model_config'] = str(model.get_config())

    # get model weights from keras object 
    def to_list(x):
        return x.tolist()

    metadata['model_weights'] = str(list(map(to_list, model.get_weights())))

    # get model state from pytorch model object
    metadata['model_state'] = None
    
    # get list of current layer types 
    layer_list, activation_list = _get_layer_names()

    # extract model architecture metadata 
    layers = []
    layers_n_params = []
    layers_shapes = []
    activations = []
    
    for i in model.layers: 
        
        # get layer names 
        if i.__class__.__name__ in layer_list:
            layers.append(i.__class__.__name__)
            layers_n_params.append(i.count_params())
            layers_shapes.append(i.output_shape)
        
        # get activation names
        if i.__class__.__name__ in activation_list: 
            activations.append(i.__class__.__name__.lower())
        if hasattr(i, 'activation') and i.activation.__name__ in activation_list:
            activations.append(i.activation.__name__)

    if hasattr(model, 'loss'):
        loss = model.loss.__class__.__name__
    else:
        loss = None
        
    if hasattr(model, 'optimizer'):
        optimizer = model.optimizer.__class__.__name__
    else:
        optimizer = None 

    model_summary_pd = model_summary_keras(model)
    
    # insert data into model architecture dict 
    model_architecture = {'layers_number': len(layers),
                          'layers_sequence': layers,
                          'layers_summary': {i:layers.count(i) for i in set(layers)},
                          'layers_n_params': layers_n_params,
                          'layers_shapes': layers_shapes,
                          'activations_sequence': activations,
                          'activations_summary': {i:activations.count(i) for i in set(activations)},
                          'loss':loss,
                          'optimizer': optimizer
                         }

    metadata['model_architecture'] = str(model_architecture)

    metadata['model_summary'] = model_summary_pd.to_json()

    metadata['memory_size'] = asizeof.asizeof(model)

    metadata['epochs'] = epochs

    # placeholder, needs evaluation engine
    metadata['eval_metrics'] = None

    # add metadata from onnx object
    # metadata['metadata_onnx'] = str(_extract_onnx_metadata(onx, framework='keras'))
    metadata['metadata_onnx'] = None
    # add metadata dict to onnx object
    
    meta = onx.metadata_props.add()
    meta.key = 'model_metadata'
    meta.value = str(metadata)

    return onx


def _pytorch_to_onnx(model, model_input, transfer_learning=None, 
                    deep_learning=None, task_type=None, 
                    epochs=None):
    
    '''Extracts metadata from pytorch model object.'''

    # TODO check whether this is a fitted pytorch model
    # isinstance...

    # generate tempfile for onnx object 
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, 'temp_file_name')

    # generate onnx file and save it to temporary path
    export(model, model_input, temp_path)

    # load onnx file from temporary path
    onx = onnx.load(temp_path)

    # generate metadata dict 
    metadata = {}

    # placeholders, need to be generated elsewhere
    metadata['model_id'] = None
    metadata['data_id'] = None
    metadata['preprocessor_id'] = None

    # infer ml framework from function call
    metadata['ml_framework'] = 'pytorch'

    # get model type from model object
    metadata['model_type'] = str(model.__class__).split('.')[-1].split("'")[0] + '()'

    # get transfer learning bool from user input
    metadata['transfer_learning'] = transfer_learning 

    # get deep learning bool from user input
    metadata['deep_learning'] = deep_learning

    # get task type from user input 
    metadata['task_type'] = task_type

    # placeholders, need to be inferred from data 
    metadata['target_distribution'] = None
    metadata['input_type'] = None
    metadata['input_shape'] = None
    metadata['input_dtypes'] = None       
    metadata['input_distribution'] = None

    # get model config dict from pytorch model object
    metadata['model_config'] = str(model.__dict__)

    # get model state from pytorch model object
    metadata['model_state'] = str(model.state_dict())

    # extract model architecture metadata
    activation_names = ['ReLU', 'Softmax']   #placeholder
    layer_names = []

    layers = []
    layers_shapes = []
    n_params = []


    for i, j  in model.__dict__['_modules'].items():

        if j._get_name() not in activation_names:

            layers.append(j._get_name())
            layers_shapes.append(j.out_features)
            weights = np.prod(j._parameters['weight'].shape)
            bias = np.prod(j._parameters['bias'].shape)
            n_params.append(weights+bias)


    activations = []
    for i, j in model.__dict__['_modules'].items():
        if str(j).split('(')[0] in activation_names:
            activations.append(str(j).split('(')[0])


    model_architecture = {'layers_number': len(layers),
                  'layers_sequence': layers,
                  'layers_summary': {i:layers.count(i) for i in set(layers)},
                  'layers_n_params': n_params,
                  'layers_shapes': layers_shapes,
                  'activations_sequence': activations,
                  'activations_summary': {i:activations.count(i) for i in set(activations)}
                 }

    metadata['model_architecture'] = str(model_architecture)

    metadata['memory_size'] = asizeof.asizeof(model)    
    metadata['epochs'] = epochs

    # placeholder, needs evaluation engine
    metadata['eval_metrics'] = None

    # add metadata from onnx object
    # metadata['metadata_onnx'] = str(_extract_onnx_metadata(onx, framework='pytorch'))
    metadata['metadata_onnx'] = None

    # add metadata dict to onnx object
    meta = onx.metadata_props.add()
    meta.key = 'model_metadata'
    meta.value = str(metadata)
    

    return onx


def model_to_onnx(model, framework, model_input=None, initial_types=None,
                  transfer_learning=None, deep_learning=None, task_type=None, 
                  epochs=None):
    
    '''Transforms sklearn, keras, or pytorch model object into ONNX format 
    and extracts model metadata dictionary. The model metadata dictionary 
    is saved in the ONNX file's metadata_props. 
    
    Parameters: 
    model: fitted sklearn, keras, or pytorch model object
    Specifies the model object that will be converted to ONNX. 
    
    framework: {"sklearn", "keras", "pytorch"}
    Specifies the machine learning framework of the model object.
    
    model_input: array_like, default=None
    Required when framework="pytorch".
    initial_types: initial types tuple, default=None
    Required when framework="sklearn".
     
    transfer_learning: bool, default=None
    Indicates whether transfer learning was used. 
    
    deep_learning: bool, default=None
    Indicates whether deep learning was used. 
    
    task_type: {"classification", "regression"}
    Indicates whether the model is a classification model or
    a regression model.
    
    Returns:
    ONNX object with model metadata saved in metadata props
    '''

    # assert that framework exists
    frameworks = ['sklearn', 'keras', 'pytorch', 'xgboost']
    assert framework in frameworks, \
    'Please choose "sklearn", "keras", "pytorch", or "xgboost".'
    
    # assert model input type THIS IS A PLACEHOLDER
    if model_input != None:
        assert isinstance(model_input, (list, pd.core.series.Series, np.ndarray, torch.Tensor)), \
        'Please format model input as XYZ.'
    
    # assert initialtypes 
    if initial_types != None:
        assert isinstance(initial_types[0][1], (skl2onnx.common.data_types.FloatTensorType)), \
        'Please use FloatTensorType as initial types.'
        
    # assert transfer_learning
    if transfer_learning != None:
        assert isinstance(transfer_learning, (bool)), \
        'Please pass boolean to indicate whether transfer learning was used.'
        
    # assert deep_learning
    if deep_learning != None:
        assert isinstance(deep_learning, (bool)), \
        'Please pass boolean to indicate whether deep learning was used.'
        
    # assert task_type
    if task_type != None:
        assert task_type in ['classification', 'regression'], \
        'Please specify task type as "classification" or "regression".'
    

    if framework == 'sklearn':
        onnx = _sklearn_to_onnx(model, initial_types=initial_types, 
                                transfer_learning=transfer_learning, 
                                deep_learning=deep_learning, 
                                task_type=task_type)
    elif framework == 'xgboost':
        onnx = _misc_to_onnx(model, initial_types=initial_types, 
                                transfer_learning=transfer_learning, 
                                deep_learning=deep_learning, 
                                task_type=task_type)
        
    elif framework == 'keras':
        onnx = _keras_to_onnx(model, transfer_learning=transfer_learning, 
                              deep_learning=deep_learning, 
                              task_type=task_type,
                              epochs=epochs)

        
    elif framework == 'pytorch':
        onnx = _pytorch_to_onnx(model, model_input=model_input,
                                transfer_learning=transfer_learning, 
                                deep_learning=deep_learning, 
                                task_type=task_type,
                                epochs=epochs)


    try: 
        rt.InferenceSession(onnx.SerializeToString())   
    except Exception as e: 
        print(e)

    return onnx



def _get_metadata(onnx_model):
    '''Fetches previously extracted model metadata from ONNX object
    and returns model metadata dict.'''
    
    # double check this 
    #assert(isinstance(onnx_model, onnx.onnx_ml_pb2.ModelProto)), \
     #"Please pass a onnx model object."
    
    try: 
        onnx_meta = onnx_model.metadata_props

        onnx_meta_dict = {'model_metadata': ''}

        for i in onnx_meta:
            onnx_meta_dict[i.key] = i.value

        onnx_meta_dict = ast.literal_eval(onnx_meta_dict['model_metadata'])
        
        #if onnx_meta_dict['model_config'] != None and \
        #onnx_meta_dict['ml_framework'] != 'pytorch':
        #    onnx_meta_dict['model_config'] = ast.literal_eval(onnx_meta_dict['model_config'])
        
        if onnx_meta_dict['model_architecture'] != None:
            onnx_meta_dict['model_architecture'] = ast.literal_eval(onnx_meta_dict['model_architecture'])
            
        if onnx_meta_dict['metadata_onnx'] != None:
            onnx_meta_dict['metadata_onnx'] = ast.literal_eval(onnx_meta_dict['metadata_onnx'])
        
        # onnx_meta_dict['model_image'] = onnx_to_image(onnx_model)

    except Exception as e:
    
        print(e)
        
        onnx_meta_dict = ast.literal_eval(onnx_meta_dict)
        
    return onnx_meta_dict



def _get_leaderboard_data(onnx_model, eval_metrics=None):
    
    if eval_metrics is not None:
        metadata = eval_metrics
    else:
        metadata = dict()
        
    metadata_raw = _get_metadata(onnx_model)

    # get list of current layer types 
    layer_list, activation_list = _get_layer_names()

    # get general model info
    metadata['ml_framework'] = metadata_raw['ml_framework']
    metadata['transfer_learning'] = metadata_raw['transfer_learning']
    metadata['deep_learning'] = metadata_raw['deep_learning']
    metadata['model_type'] = metadata_raw['model_type']


    # get neural network metrics
    if metadata_raw['ml_framework'] == 'keras' or metadata_raw['model_type'] in ['MLPClassifier', 'MLPRegressor']:
        metadata['depth'] = metadata_raw['model_architecture']['layers_number']
        metadata['num_params'] = sum(metadata_raw['model_architecture']['layers_n_params'])

        for i in layer_list:
            if i in metadata_raw['model_architecture']['layers_summary']:
                metadata[i.lower()+'_layers'] = metadata_raw['model_architecture']['layers_summary'][i]
            else:
                metadata[i.lower()+'_layers'] = 0

        for i in activation_list:
            if i in metadata_raw['model_architecture']['activations_summary']:
                if i.lower()+'_act' in metadata:
                    metadata[i.lower()+'_act'] += metadata_raw['model_architecture']['activations_summary'][i]
                else:    
                    metadata[i.lower()+'_act'] = metadata_raw['model_architecture']['activations_summary'][i]
            else:
                if i.lower()+'_act' not in metadata:
                    metadata[i.lower()+'_act'] = 0
                
        metadata['loss'] = metadata_raw['model_architecture']['loss']
        metadata['optimizer'] = metadata_raw['model_architecture']["optimizer"]
        metadata['model_config'] = metadata_raw['model_config']
        metadata['epochs'] = metadata_raw['epochs']
        metadata['memory_size'] = metadata_raw['memory_size']



    # get sklearn model metrics
    elif metadata_raw['ml_framework'] == 'sklearn' or metadata_raw['ml_framework'] == 'xgboost':
        metadata['depth'] = 0

        try:
            metadata['num_params'] = sum(metadata_raw['model_architecture']['layers_n_params'])
        except:
            metadata['num_params'] = 0

        for i in layer_list:
            metadata[i.lower()+'_layers'] = 0

        for i in activation_list:
            metadata[i.lower()+'_act'] = 0

        metadata['loss'] = None

        try:
            metadata['optimizer'] = metadata_raw['model_architecture']['optimizer']
        except:
            metadata['optimizer'] = None

        try:
            metadata['model_config'] = metadata_raw['model_config']
        except:
            metadata['model_config'] = None
    
    return metadata
    


def _model_summary(meta_dict, from_onnx=False):
    '''Creates model summary table from model metadata dict.'''
    
    assert(isinstance(meta_dict, dict)), \
    "Please pass valid metadata dict."
    
    assert('model_architecture' in meta_dict.keys()), \
    "Please make sure model architecture data is included."

    if from_onnx == True:
        model_summary = pd.read_json(meta_dict['metadata_onnx']["model_summary"])
    else:
        model_summary = pd.read_json(meta_dict["model_summary"])
       
    return model_summary



def onnx_to_image(model):
    '''Creates model graph image in pydot format.'''
    
    OP_STYLE = {
    'shape': 'box',
    'color': '#0F9D58',
    'style': 'filled',
    'fontcolor': '#FFFFFF'
    }
    
    pydot_graph = GetPydotGraph(
        model.graph,
        name=model.graph.name,
        rankdir='TB',
        node_producer=GetOpNodeProducer(
            embed_docstring=False,
            **OP_STYLE
        )
    )
    
    return pydot_graph

def inspect_model_aws(apiurl, version=None):
    if all(["AWS_ACCESS_KEY_ID" in os.environ, 
            "AWS_SECRET_ACCESS_KEY" in os.environ,
            "AWS_REGION" in os.environ, 
           "username" in os.environ, 
           "password" in os.environ]):
        pass
    else:
        return print("'Inspect Model' unsuccessful. Please provide credentials with set_credentials().")

    aws_client = get_aws_client() 

    onnx_model = _get_onnx_from_bucket(apiurl, aws_client, version=version)

    meta_dict = _get_metadata(onnx_model)

    if meta_dict['ml_framework'] == 'keras':
        inspect_pd = _model_summary(meta_dict)
        
    elif meta_dict['ml_framework'] in ['sklearn', 'xgboost']:
        model_config = meta_dict["model_config"]
        model_config = ast.literal_eval(model_config)
        inspect_pd = pd.DataFrame({'param_name': model_config.keys(),
                                   'param_value': model_config.values()})
    
    return inspect_pd

def inspect_model_lambda(apiurl, version=None):
    if all(["username" in os.environ, 
           "password" in os.environ]):
        pass
    else:
        return print("'Inspect Model' unsuccessful. Please provide credentials with set_credentials().")

    post_dict = {"y_pred": [],
               "return_eval": "False",
               "return_y": "False",
               "inspect_model": "True",
               "version": version}
    
    headers = { 'Content-Type':'application/json', 'authorizationToken': os.environ.get("AWS_TOKEN"),} 

    apiurl_eval=apiurl[:-1]+"eval"

    inspect_json = requests.post(apiurl_eval,headers=headers,data=json.dumps(post_dict)) 

    inspect_pd = pd.DataFrame(json.loads(inspect_json.text))

    return inspect_pd


def inspect_model_dict(apiurl, version=None):

    if all(["AWS_ACCESS_KEY_ID" in os.environ, 
            "AWS_SECRET_ACCESS_KEY" in os.environ,
            "AWS_REGION" in os.environ, 
           "username" in os.environ, 
           "password" in os.environ]):
        pass
    else:
        return print("'Inspect Model' unsuccessful. Please provide credentials with set_credentials().")

    aws_client=get_aws_client(aws_key=os.environ.get('AWS_ACCESS_KEY_ID'), 
                              aws_secret=os.environ.get('AWS_SECRET_ACCESS_KEY'), 
                              aws_region=os.environ.get('AWS_REGION'))

    # Get bucket and model_id for user
    response, error = run_function_on_lambda(
        apiurl, **{"delete": "FALSE", "versionupdateget": "TRUE"}
    )
    if error is not None:
        raise error

    _, bucket, model_id = json.loads(response.content.decode("utf-8"))

    key = model_id+'/inspect_pd.json'
    
    try:
      resp = aws_client['client'].get_object(Bucket=bucket, Key=key)
      data = resp.get('Body').read()
      model_dict = json.loads(data)
    except Exception as e:
        print(e)

    ml_framework = model_dict.get(str(version))['ml_framework']
    model_type = model_dict.get(str(version))['model_type']
    inspect_pd = pd.DataFrame(model_dict.get(str(version))['model_dict'])
    
    return inspect_pd



def inspect_model(apiurl, version=None):
    if all(["username" in os.environ, 
           "password" in os.environ]):
        pass
    else:
        return print("'Inspect Model' unsuccessful. Please provide credentials with set_credentials().")

    try:
        inspect_pd = inspect_model_lambda(apiurl, version)
    except:

        try: 
            inspect_pd = inspect_model_dict(apiurl, version)
        except: 
            inspect_pd = inspect_model_aws(apiurl, version)
    
    return inspect_pd


def compare_models_dict(apiurl, version_list=None, 
    by_model_type=None, best_model=None, verbose=1):
    
    if not isinstance(version_list, list):
        raise Exception("Argument 'version' must be a list.")
    
    if all(["AWS_ACCESS_KEY_ID" in os.environ, 
            "AWS_SECRET_ACCESS_KEY" in os.environ,
            "AWS_REGION" in os.environ, 
           "username" in os.environ, 
           "password" in os.environ]):
        pass
    else:
        return print("'Compare Models' unsuccessful. Please provide credentials with set_credentials().")

    aws_client=get_aws_client(aws_key=os.environ.get('AWS_ACCESS_KEY_ID'), 
                              aws_secret=os.environ.get('AWS_SECRET_ACCESS_KEY'), 
                              aws_region=os.environ.get('AWS_REGION'))

    # Get bucket and model_id for user
    response, error = run_function_on_lambda(
        apiurl, **{"delete": "FALSE", "versionupdateget": "TRUE"}
    )
    if error is not None:
        raise error

    _, bucket, model_id = json.loads(response.content.decode("utf-8"))

    key = model_id+'/inspect_pd.json'
    
    try:
      resp = aws_client['client'].get_object(Bucket=bucket, Key=key)
      data = resp.get('Body').read()
      model_dict = json.loads(data)
    except Exception as e:
        print(e)

    ml_framework_list = [model_dict[str(i)]['ml_framework'] for i in version_list]
    model_type_list = [model_dict[str(i)]['model_type'] for i in version_list]
    model_dict_list = [model_dict[str(i)]['model_dict'] for i in version_list]

    if not all(x==ml_framework_list[0] for x in ml_framework_list):
        raise Exception("Incongruent frameworks. Please compare models from the same ML frameworks.")
        

    if ml_framework_list[0] == 'sklearn':

        comp_dict_out = {}
        
        for i in version_list: 
            
            temp_pd = pd.DataFrame(model_dict[str(i)]['model_dict'])
            temp_pd.columns = ['param_name', 'default_value', "model_version_"+str(i)]

            if model_dict[str(i)]['model_type'] in comp_dict_out.keys():

                comp_pd = comp_dict_out[model_dict[str(i)]['model_type']]
                comp_pd = comp_pd.merge(temp_pd.drop('default_value', axis=1), on='param_name')

                comp_dict_out[model_dict[str(i)]['model_type']] = comp_pd

            else:
                comp_dict_out[model_dict[str(i)]['model_type']] = temp_pd

        return comp_dict_out

            
    if ml_framework_list[0] == 'keras':

        comp_pd = pd.DataFrame()

        for i in version_list: 

            temp_pd = pd.DataFrame(model_dict[str(i)]['model_dict'])

            temp_pd.iloc[:,2] = temp_pd.iloc[:,2].astype(str)

            if verbose == 0: 
                temp_pd = temp_pd[['Layer']]
            elif verbose == 1: 
                temp_pd = temp_pd[['Layer', 'Shape', 'Params']]
            elif verbose == 2: 
                temp_pd = temp_pd[['Name', 'Layer', 'Shape', 'Params', 'Connect']]
            elif verbose == 3: 
                temp_pd = temp_pd[['Name', 'Layer', 'Shape', 'Params', 'Connect', 'Activation']]

            temp_pd = temp_pd.add_prefix('Model_'+str(i)+'_')    
            comp_pd = pd.concat([comp_pd, temp_pd], axis=1)

        comp_dict_out = {"Sequential": comp_pd}
        
        return comp_dict_out


def color_pal_assign(val):
  import pandas as pd
  
  # create Pandas Series with default index values
  # default index ranges is from 0 to len(list) - 1
  layer_name_df =  pd.DataFrame(['AbstractRNNCell',
  'Activation',
  'ActivityRegularization',
  'Add',
  'AdditiveAttention',
  'AlphaDropout',
  'Attention',
  'Average',
  'AveragePooling1D',
  'AveragePooling2D',
  'AveragePooling3D',
  'AvgPool1D',
  'AvgPool2D',
  'AvgPool3D',
  'BatchNormalization',
  'Bidirectional',
  'CategoryEncoding',
  'CenterCrop',
  'Concatenate',
  'Conv1D',
  'Conv1DTranspose',
  'Conv2D',
  'Conv2DTranspose',
  'Conv3D',
  'Conv3DTranspose',
  'ConvLSTM1D',
  'ConvLSTM2D',
  'ConvLSTM3D',
  'Convolution1D',
  'Convolution1DTranspose',
  'Convolution2D',
  'Convolution2DTranspose',
  'Convolution3D',
  'Convolution3DTranspose',
  'Cropping1D',
  'Cropping2D',
  'Cropping3D',
  'Dense',
  'DenseFeatures',
  'DepthwiseConv2D',
  'Discretization',
  'Dot',
  'Dropout',
  'Embedding',
  'Flatten',
  'GRU',
  'GRUCell',
  'GaussianDropout',
  'GaussianNoise',
  'GlobalAveragePooling1D',
  'GlobalAveragePooling2D',
  'GlobalAveragePooling3D',
  'GlobalAvgPool1D',
  'GlobalAvgPool2D',
  'GlobalAvgPool3D',
  'GlobalMaxPool1D',
  'GlobalMaxPool2D',
  'GlobalMaxPool3D',
  'GlobalMaxPooling1D',
  'GlobalMaxPooling2D',
  'GlobalMaxPooling3D',
  'Hashing',
  'Input',
  'InputLayer',
  'InputSpec',
  'IntegerLookup',
  'LSTM',
  'LSTMCell',
  'Lambda',
  'Layer',
  'LayerNormalization',
  'LocallyConnected1D',
  'LocallyConnected2D',
  'Masking',
  'MaxPool1D',
  'MaxPool2D',
  'MaxPool3D',
  'MaxPooling1D',
  'MaxPooling2D',
  'MaxPooling3D',
  'Maximum',
  'Minimum',
  'MultiHeadAttention',
  'Multiply',
  'Normalization',
  'Permute',
  'RNN',
  'RandomContrast',
  'RandomCrop',
  'RandomFlip',
  'RandomHeight',
  'RandomRotation',
  'RandomTranslation',
  'RandomWidth',
  'RandomZoom',
  'RepeatVector',
  'Rescaling',
  'Reshape',
  'Resizing',
  'SeparableConv1D',
  'SeparableConv2D',
  'SeparableConvolution1D',
  'SeparableConvolution2D',
  'SimpleRNN',
  'SimpleRNNCell',
  'SpatialDropout1D',
  'SpatialDropout2D',
  'SpatialDropout3D',
  'StackedRNNCells',
  'StringLookup',
  'Subtract',
  'TextVectorization',
  'TimeDistributed',
  'UpSampling1D',
  'UpSampling2D',
  'UpSampling3D',
  'Wrapper',
  'ZeroPadding1D',
  'ZeroPadding2D',
  'ZeroPadding3D'])

  layernamelist=list(layer_name_df[0])
  import seaborn as sns
  paldata=sns.color_palette("Pastel2", len(layernamelist)).as_hex()

  if val in layernamelist: 
      valindex=layernamelist.index(val)
      if any([val=="Concatenate",val=="Conv2D"]):
        valindex=valindex+4
      else:
        pass
      palvalue=paldata[valindex]
  else:
     pass
  color = palvalue if val in layernamelist else 'white'
  return 'background: %s' % color

def stylize_model_comparison(comp_dict_out):


    if 'Sequential' in comp_dict_out.keys():

        df_styled = comp_dict_out['Sequential'].style.applymap(color_pal_assign)

        df_styled = df_styled.set_properties(**{'color': 'black'})

        df_styled = df_styled.set_caption('Model type: ' + 'Neural Network').set_table_styles([{'selector': 'caption',
            'props': [('color', 'white'), ('font-size', '18px')]}])

        df_styled = df_styled.set_properties(**{'color': 'black'})

        df_styled = df_styled.set_caption('Model type: ' + 'Neural Network').set_table_styles([{'selector': 'caption',
            'props': [('color', 'black'), ('font-size', '18px')]}])

        display(HTML(df_styled.render()))


    else:

        for i in comp_dict_out.keys():

            comp_pd = comp_dict_out[i]

            df_styled = comp_pd.style.apply(lambda x: ["background: tomato" if v != x.iloc[0] else "" for v in x], 
                axis = 1, subset=comp_pd.columns[1:])

            df_styled = df_styled.set_caption('Model type: ' + i).set_table_styles([{'selector': 'caption',
                'props': [('color', 'black'), ('font-size', '18px')]}])

            display(HTML(df_styled.render()))
            print('\n\n')


def compare_models_aws(apiurl, version_list=None, 
    by_model_type=None, best_model=None, verbose=3):
    
    if not isinstance(version_list, list):
        raise Exception("Argument 'version' must be a list.")
    
    if all(["AWS_ACCESS_KEY_ID" in os.environ, 
            "AWS_SECRET_ACCESS_KEY" in os.environ,
            "AWS_REGION" in os.environ, 
           "username" in os.environ, 
           "password" in os.environ]):
        pass
    else:
        return print("'Compare Models' unsuccessful. Please provide credentials with set_credentials().")

    aws_client = get_aws_client()
    
    models_dict = {}
    
    for i in version_list: 
        
        onnx_model = _get_onnx_from_bucket(apiurl, aws_client, version=i)
        meta_dict = _get_metadata(onnx_model)
        
        models_dict[i] = meta_dict
        
    ml_framework_list = [models_dict[i]['ml_framework'] for i in models_dict]
    model_type_list = [models_dict[i]['model_type'] for i in models_dict]
    
    if not all(x==ml_framework_list[0] for x in ml_framework_list):
        raise Exception("Incongruent frameworks. Please compare models from the same ML frameworks.")
        
    if not all(x==model_type_list[0] for x in model_type_list):
        raise Exception("Incongruent model types. Please compare models of the same model type.")
    
    if ml_framework_list[0] == 'sklearn':
        
        model_type = model_type_list[0]
        model_class = model_from_string(model_type)
        default = model_class()
        default_config = default.get_params()
        
        comp_pd = pd.DataFrame({'param_name': default_config.keys(),
                           'param_value': default_config.values()})
        
        for i in version_list: 
            
            temp_pd = inspect_model(apiurl, version=i)
            comp_pd = comp_pd.merge(temp_pd, on='param_name')
        
        comp_pd.columns = ['param_name', 'model_default'] + ["Model_"+str(i) for i in version_list]
        
        df_styled = comp_pd.style.apply(lambda x: ["background: tomato" if v != x.iloc[0] else "" for v in x], 
                                        axis = 1, subset=comp_pd.columns[1:])

        
    if ml_framework_list[0] == 'keras':

        comp_pd = pd.DataFrame()

        for i in version_list: 

            temp_pd = inspect_model(apiurl, version=i)

            temp_pd = temp_pd.iloc[:,0:verbose]

            temp_pd = temp_pd.add_prefix('Model_'+str(i)+'_')    
            comp_pd = pd.concat([comp_pd, temp_pd], axis=1, ignore_index=True)

        layer_names = _get_layer_names()

        dense_layers = [i for i in layer_names[0] if 'Dense' in i]
        df_styled = df_styled.style.apply(lambda x: ["background: #DFFF00" if v in dense_layers else "" for v in x], 
                                axis = 1)
        drop_layers = [i for i in layer_names[0] if 'Dropout' in i]
        df_styled = df_styled.apply(lambda x: ["background: #FFBF00" if v in drop_layers else "" for v in x], 
                                axis = 1)
        conv_layers = [i for i in layer_names[0] if 'Conv' in i]
        df_styled = df_styled.apply(lambda x: ["background: #FF7F50" if v in conv_layers else "" for v in x], 
                                axis = 1)
        seq_layers = [i for i in layer_names[0] if 'RNN' in i or 'LSTM' in i or 'GRU' in i] + ['Bidirectional']
        df_styled = df_styled.apply(lambda x: ["background: #DE3163" if v in seq_layers else "" for v in x], 
                                axis = 1)
        pool_layers = [i for i in layer_names[0] if 'Pool' in i]
        df_styled = df_styled.apply(lambda x: ["background: #9FE2BF" if v in pool_layers else "" for v in x], 
                                axis = 1)
        rest_layers = [i for i in layer_names[0] if i not in dense_layers+drop_layers+conv_layers+seq_layers+pool_layers]
        df_styled = df_styled.apply(lambda x: ["background: lightgrey" if v in rest_layers else "" for v in x], 
                            axis = 1)

    df_styled = df_styled.style.set_properties(**{'color': 'lawngreen'})

    return df_styled


def compare_models_lambda(apiurl, version_list="None", 
    by_model_type=None, best_model=None, verbose=1):
    if all(["username" in os.environ, 
           "password" in os.environ]):
        pass
    else:
        return print("'Inspect Model' unsuccessful. Please provide credentials with set_credentials().")

    post_dict = {"y_pred": [],
               "return_eval": "False",
               "return_y": "False",
               "inspect_model": "False",
               "version": "None", 
               "compare_models": "True",
               "version_list": version_list,
               "verbose": verbose}
    
    headers = { 'Content-Type':'application/json', 'authorizationToken': os.environ.get("AWS_TOKEN"),} 

    apiurl_eval=apiurl[:-1]+"eval"

    compare_json = requests.post(apiurl_eval,headers=headers,data=json.dumps(post_dict)) 

    compare_dict = json.loads(compare_json.text)

    comp_dict_out = {i: pd.DataFrame(json.loads(compare_dict[i])) for i in compare_dict}

    return comp_dict_out


def compare_models(apiurl, version_list="None", 
    by_model_type=None, best_model=None, verbose=3):

    if all(["username" in os.environ, 
           "password" in os.environ]):
        pass
    else:
        return print("'Inspect Model' unsuccessful. Please provide credentials with set_credentials().")

    if len(version_list) != len(set(version_list)):
        return print("Model comparison failed. Version list contains duplicates.")
    
    try: 
        compare_pd = compare_models_lambda(apiurl, version_list, 
            by_model_type, best_model, verbose)

    except: 

        try: 
            compare_pd = compare_models_dict(apiurl, version_list, 
            by_model_type, best_model, verbose)
        except:

            compare_pd = compare_models_aws(apiurl, version_list, 
                by_model_type, best_model, verbose)
    
    return compare_pd

def _get_onnx_from_string(onnx_string):
    # generate tempfile for onnx object 
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, 'temp_file_name')

    # save onnx to temporary path
    with open(temp_path, "wb") as f:
        f.write(onnx_string)

    # load onnx file from temporary path
    onx = onnx.load(temp_path)
    return onx

def _get_onnx_from_bucket(apiurl, aws_client, version=None):

    # generate name of onnx model in bucket
    onnx_model_name = "/onnx_model_v{version}.onnx".format(version = version)

    # Get bucket and model_id for user
    response, error = run_function_on_lambda(
        apiurl, **{"delete": "FALSE", "versionupdateget": "TRUE"}
    )
    if error is not None:
        raise error

    _, bucket, model_id = json.loads(response.content.decode("utf-8"))

    try:
        onnx_string = aws_client["client"].get_object(
            Bucket=bucket, Key=model_id + onnx_model_name
        )

        onnx_string = onnx_string['Body'].read()

    except Exception as err:
        raise err

    onx = _get_onnx_from_string(onnx_string)

    return onx


def instantiate_model(apiurl, version=None, trained=False, determinism=False):
    # Confirm that creds are loaded, print warning if not
    if all(["username" in os.environ, 
          "password" in os.environ]):
      pass
    else:
      return print("'Submit Model' unsuccessful. Please provide credentials with set_credentials().")

    post_dict = {
        "y_pred": [],
        "return_eval": "False",
        "return_y": "False",
        "inspect_model": "False",
        "version": "None", 
        "compare_models": "False",
        "version_list": "None",
        "get_leaderboard": "False",
        "instantiate_model": "True",
        "determinism": determinism,
        "trained": trained,
        "model_version": version
    }

    headers = { 'Content-Type':'application/json', 'authorizationToken': os.environ.get("AWS_TOKEN"),} 

    apiurl_eval=apiurl[:-1]+"eval"

    resp = requests.post(apiurl_eval,headers=headers,data=json.dumps(post_dict)) 

    resp_dict = json.loads(resp.text)

    if determinism:
        if resp_dict['determinism_env'] != None:
            set_determinism_env(resp_dict['determinism_env'])
            print("Your determinism environment is successfully setup")
        else:
            print("Determinism environment is not found")

    print("Instantiate the model from metadata..")
    
    meta_dict = resp_dict['model_metadata']
    model_config = ast.literal_eval(meta_dict['model_config'])
    ml_framework = meta_dict['ml_framework']

    if ml_framework == 'sklearn':
        if trained == False or determinism == True:
            model_type = meta_dict['model_type']
            model_class = model_from_string(model_type)
            model = model_class(**model_config)

        elif trained == True:
            model_pkl = None
            if "https://" in meta_dict['model_weights']: # presigned
                temp = tempfile.mkdtemp()
                temp_path = temp + "/" + "onnx_model_v{}.onnx".format(version)
            
                # Get leaderboard
                status = wget.download(meta_dict['model_weights'], out=temp_path)
                onnx_model = onnx.load(temp_path)
                model_pkl = _get_metadata(onnx_model)['model_weights']
            else:
                model_pkl = meta_dict['model_weights'].encode("ISO-8859-1")

            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, 'temp_file_name')

            with open(temp_path, "wb") as f:
                f.write(model_pkl)

            with open(temp_path, 'rb') as f:
                model = pickle.load(f)

    if ml_framework == 'keras':
        if trained == False or determinism == True:
            model = tf.keras.Sequential().from_config(model_config)

        elif trained == True:
            model_weights = None
            if "https://" in meta_dict['model_weights']: # presigned
                temp = tempfile.mkdtemp()
                temp_path = temp + "/" + "onnx_model_v{}.onnx".format(version)
            
                # Get leaderboard
                status = wget.download(meta_dict['model_weights'], out=temp_path)
                onnx_model = onnx.load(temp_path)
                model_weights = json.loads(_get_metadata(onnx_model)['model_weights'])
            else:
                model_weights = json.loads(meta_dict['model_weights'])
            
            model = tf.keras.Sequential().from_config(model_config)
            
            def to_array(x):
                return np.array(x, dtype="float32")

            model_weights = list(map(to_array, model_weights))

            model.set_weights(model_weights)

    print("Your model is successfully instantiated.")
    return model

# def instantiate_model(apiurl, version=None, trained=False):
#     if all(["AWS_ACCESS_KEY_ID" in os.environ, 
#             "AWS_SECRET_ACCESS_KEY" in os.environ,
#             "AWS_REGION" in os.environ, 
#             "username" in os.environ, 
#             "password" in os.environ]):
#         pass
#     else:
#         return print("'Instantiate Model' unsuccessful. Please provide credentials with set_credentials().")

#     aws_client = get_aws_client()   
#     onnx_model = _get_onnx_from_bucket(apiurl, aws_client, version=version)
#     meta_dict = _get_metadata(onnx_model)

#     # get model config 
#     model_config = ast.literal_eval(meta_dict['model_config'])
#     ml_framework = meta_dict['ml_framework']
    
#     if ml_framework == 'sklearn':

#         if trained == False:
#             model_type = meta_dict['model_type']
#             model_class = model_from_string(model_type)
#             model = model_class(**model_config)

#         if trained == True:
            
#             model_pkl = meta_dict['model_weights']

#             temp_dir = tempfile.gettempdir()
#             temp_path = os.path.join(temp_dir, 'temp_file_name')

#             with open(temp_path, "wb") as f:
#                 f.write(model_pkl)

#             with open(temp_path, 'rb') as f:
#                 model = pickle.load(f)


#     if ml_framework == 'keras':

#         if trained == False:
#             model = tf.keras.Sequential().from_config(model_config)

#         if trained == True: 
#             model = tf.keras.Sequential().from_config(model_config)
#             model_weights = json.loads(meta_dict['model_weights'])

#             def to_array(x):
#                 return np.array(x, dtype="float32")

#             model_weights = list(map(to_array, model_weights))

#             model.set_weights(model_weights)

#     return model


def _get_layer_names():

    activation_list = [i for i in dir(tf.keras.activations)]
    activation_list = [i for i in activation_list if callable(getattr(tf.keras.activations, i))]
    activation_list = [i for i in activation_list if  not i.startswith("_")]
    activation_list.remove('deserialize')
    activation_list.remove('get')
    activation_list.remove('linear')
    activation_list = activation_list+['ReLU', 'Softmax', 'LeakyReLU', 'PReLU', 'ELU', 'ThresholdedReLU']


    layer_list = [i for i in dir(tf.keras.layers)]
    layer_list = [i for i in dir(tf.keras.layers) if callable(getattr(tf.keras.layers, i))]
    layer_list = [i for i in layer_list if not i.startswith("_")]
    layer_list = [i for i in layer_list if re.match('^[A-Z]', i)]
    layer_list = [i for i in layer_list if i.lower() not in [i.lower() for i in activation_list]]

    return layer_list, activation_list


def _get_sklearn_modules():
    
    import sklearn

    sklearn_modules = ['ensemble', 'gaussian_process', 'isotonic',
                       'linear_model', 'mixture', 'multiclass', 'naive_bayes', 
                       'neighbors', 'neural_network', 'svm', 'tree']

    models_modules_dict = {}

    for i in sklearn_modules:
        models_list = [j for j in dir(eval('sklearn.'+i)) if callable(getattr(eval('sklearn.'+i), j))]
        models_list = [j for j in models_list if re.match('^[A-Z]', j)]

        for k in models_list: 
            models_modules_dict[k] = 'sklearn.'+i
    
    return models_modules_dict



def model_from_string(model_type):
    models_modules_dict = _get_sklearn_modules()
    module = models_modules_dict[model_type]
    model_class = getattr(importlib.import_module(module), model_type)
    return model_class


def print_y_stats(y_stats): 

  print("y_test example: ", y_stats['ytest_example'])
  print("y_test class labels", y_stats['class_labels'])
  print("y_test class balance", y_stats['class_balance'])
  print("y_test label dtypes", y_stats['label_dtypes'])


def inspect_y_test(apiurl):

  # Confirm that creds are loaded, print warning if not
  if all(["username" in os.environ, 
          "password" in os.environ]):
      pass
  else:
      return print("'Submit Model' unsuccessful. Please provide credentials with set_credentials().")

  post_dict = {"y_pred": [],
               "return_eval": "False",
               "return_y": "True"}
    
  headers = { 'Content-Type':'application/json', 'authorizationToken': os.environ.get("AWS_TOKEN"),} 

  apiurl_eval=apiurl[:-1]+"eval"

  y_stats = requests.post(apiurl_eval,headers=headers,data=json.dumps(post_dict)) 

  y_stats_dict = json.loads(y_stats.text)

  # print_y_stats(y_stats_dict)

  return y_stats_dict


def model_summary_keras(model):

    # extract model architecture metadata 
    layer_names = []
    layer_types = []
    layer_n_params = []
    layer_shapes = []
    layer_connect = []
    activations = []


    for i in model.layers: 

        try:
            layer_names.append(i.name)
        except:
            layer_names.append(None)

        try:
            layer_types.append(i.__class__.__name__)
        except:
            layer_types.append(None)

        try:
            layer_shapes.append(i.output_shape)
        except:
            layer_shapes.append(None)

        try:
            layer_n_params.append(i.count_params())
        except:
            layer_n_params.append(None)

        try:
            if isinstance(i.inbound_nodes[0].inbound_layers, list):
              layer_connect.append([x.name for x in i.inbound_nodes[0].inbound_layers])
            else: 
              layer_connect.append(i.inbound_nodes[0].inbound_layers.name)
        except:
            layer_connect.append(None)

        try: 
            activations.append(i.activation.__name__)
        except:
            activations.append(None)


    model_summary = pd.DataFrame({"Name": layer_names,
    "Layer": layer_types,
    "Shape": layer_shapes,
    "Params": layer_n_params,
    "Connect": layer_connect,
    "Activation": activations})

    return model_summary


def model_graph_keras(model):

    # extract model architecture metadata 
    layer_names = []
    layer_types = []
    layer_n_params = []
    layer_shapes = []
    layer_connect = []
    activations = []

    graph_nodes = []
    graph_edges = []


    for i in model.layers: 

        try:
            layer_name = i.name
        except:
            layer_name = None
        finally:
            layer_names.append(layer_name)


        try:
            layer_type = i.__class__.__name__
        except:
            layer_type = None
        finally:
            layer_types.append(layer_type)

        try:
            layer_shape = i.output_shape
        except:
            layer_shape = None
        finally:
            layer_shapes.append(layer_shape)


        try:
            layer_params = i.count_params()
        except:
            layer_params = None
        finally:
            layer_n_params.append(layer_params)


        try:
            if isinstance(i.inbound_nodes[0].inbound_layers, list):
              layer_input = [x.name for x in i.inbound_nodes[0].inbound_layers]
            else: 
              layer_input = i.inbound_nodes[0].inbound_layers.name
        except:
            layer_connect = None
        finally:
            layer_connect.append(layer_input)


        try: 
            activation = i.activation.__name__
        except:
            activation = None
        finally:
            activations.append(activation)

        layer_color = color_pal_assign(layer_type)
        layer_color =  layer_color.split(' ')[-1]


        graph_nodes.append((layer_name, {"label": layer_type + '\n' + str(layer_shape),
                                         "URL": "https://keras.io/search.html?query="+layer_type.lower(),
                                         "color": layer_color,
                                         "style": "bold",
                                    "Name": layer_name,
                                    "Layer": layer_type,
                                    "Shape": layer_shape,
                                    "Params": layer_params,
                                    "Activation": activation}))
        
        if isinstance(layer_input, list):
            for i in layer_input:
                graph_edges.append((i, layer_name))
        else:
            graph_edges.append((layer_input, layer_name))

    G = nx.DiGraph()
    G.add_nodes_from(graph_nodes)
    G.add_edges_from(graph_edges)

    G_pydot = nx.drawing.nx_pydot.to_pydot(G)

    return G_pydot


def plot_keras(model):

    G =  model_graph_keras(model)

    display(SVG(G.create_svg()))
