import wandb
import random
import numpy as np
import tensorflow as tf
import tensorflow.keras
from tensorflow import keras
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from IPython.display import Image, display


def make_gradcam_heatmap(model, m_name, img_array, pred_index=None):
    """
    GRADient-weighted Class Activation Mapping (Grad-CAM)

    We let the gradients of any target concept score (logits for any class of interest) flow
    into the final convolutional layer. We can then compute an importance score based on
    the gradients and produce a coarse localization map highlighting the important regions
    in the image for predicting that concept.
    """
    img_array = img_array[np.newaxis, :]

    if 'VGG16' in m_name:
        last_conv_layer = "block5_conv3"
        mode = 'centering'
    elif 'InceptionV3' in m_name:
        last_conv_layer = "conv2d_296"
        mode = 'sample_wise_scaling'
    elif 'ResNet50V2' in m_name:
        last_conv_layer = "conv5_block3_3_conv"
        mode = 'sample_wise_scaling'
    elif 'InceptionResNetV2' in m_name:
        last_conv_layer = "conv_7b_ac"
        mode = 'sample_wise_scaling'
    elif 'Densenet201' in m_name:
        last_conv_layer = "conv5_block32_2_conv"
        mode = 'scale_std'
    elif 'EfficientNetV2B3' in m_name:
        # efficientnetv2-b3
        last_conv_layer = "top_conv"
        mode = None
    else:
        last_conv_layer = "last_conv"
    
    model.layers[-1].activation = None
    # First, we create a model that maps the input image to the activations
    # of the last conv layer as well as the output predictions
    for layer in model.layers:
        if "Functional" == layer.__class__.__name__:
            convs = [l for l in layer.layers if l.name == last_conv_layer]
            inputs = [l for l in layer.layers if "input" in l.name]
    last_conv = convs[0]
    inputs_inter = inputs[0]

    if type(mode) != str:
        inputs = mode(model.inputs)
    else:
        inputs = preprocess_image(model.inputs, mode)
    
    print(inputs_inter.name)
    print(last_conv)
    print(last_conv.name)
    print(model.inputs)
    
    grad_model = tf.keras.models.Model(
        #Model(inputs=[in_layer1, in_layer2], outputs=[out_layer])
        # pret_efficienet
        #[model.inputs], [model.layers[1].inbound_nodes[0].output_tensors, model.output]
        [inputs], [last_conv.output, model.output]
        #[inputs], [last_conv.output, model.output]
    )
    #inputs = Keras.Input(shape=(128, 128, 3))
    
    # Then, we compute the gradient of the top predicted class for our input image
    # with respect to the activations of the last conv layer
    with tf.GradientTape() as tape:
        #img_array = tf.cast(img_array, tf.float32)
        last_conv_layer_output, preds = grad_model(img_array)
        # watch the conv_output_values
        tape.watch(last_conv_layer_output)
        if pred_index is None:
            pred_index = tf.argmax(preds[0])
        class_channel = preds[:, pred_index]

    # This is the gradient of the output neuron (top predicted or chosen)
    # with regard to the output feature map of the last conv layer
    grads = tape.gradient(class_channel, last_conv_layer_output)
    print(f"Grads shape : {grads.shape}")

    # This is a vector where each entry is the mean intensity of the gradient
    # over a specific feature map channel
    pooled_grads = tf.reduce_mean(grads, axis=(0, 1, 2))
    print("pooled_grads shape : ", pooled_grads.shape)

    # We multiply each channel in the feature map array
    # by "how important this channel is" with regard to the top predicted class
    # then sum all the channels to obtain the heatmap class activation
    last_conv_layer_output = last_conv_layer_output[0]
    heatmap = last_conv_layer_output @ pooled_grads[..., tf.newaxis]
    heatmap = tf.squeeze(heatmap)

    # For visualization purpose, we will also normalize the heatmap between 0 & 1
    heatmap = tf.maximum(heatmap, 0) / tf.math.reduce_max(heatmap)
    return heatmap.numpy()


def save_and_display_gradcam(args, model, m_name, x_test, n_img, model_metrics_dir, alpha=0.4):
    print(f"Displaying Grad-CAM for {n_img} images")
    print(f"X test shape is : {x_test.shape}")
    print(f"Model:{m_name}")

    img_ids = random.sample(range(x_test.shape[0]), n_img)

    if args.wandb:
        TABLE_NAME = "gradcam_visualization"
        columns = ["image", "heat_map", "img + gradcam"]
        grad_cam_table = wandb.Table(columns=columns)

    for id in img_ids:
        img = x_test[id]
        heatmap = make_gradcam_heatmap(model, m_name, img)
        # Rescale heatmap to a range 0-255
        heatmap = np.uint8(255 * heatmap)
        # Use jet colormap to colorize heatmap
        jet = cm.get_cmap("jet")
        # Use RGB values of the colormap
        jet_colors = jet(np.arange(256))[:, :3]
        jet_heatmap = jet_colors[heatmap]
        # Create an image with RGB colorized heatmap
        jet_heatmap = keras.preprocessing.image.array_to_img(jet_heatmap)
        jet_heatmap = jet_heatmap.resize((img.shape[1], img.shape[0]))
        jet_heatmap = keras.preprocessing.image.img_to_array(jet_heatmap)
        # Superimpose the heatmap on original image
        superimposed_img = jet_heatmap * alpha + img
        superimposed_img = keras.preprocessing.image.array_to_img(superimposed_img)

        # Save the superimposed image
        superimposed_img.save(f"{model_metrics_dir}/img_{id}.jpg")

        # Display Grad CAM
        #plt.imshow(superimposed_img)
        #plt.show()

        if args.wandb:
            row = [wandb.Image(img), #,caption=np.argmax(predictions[i])),
                    wandb.Image(heatmap),
                    wandb.Image(superimposed_img)]
            grad_cam_table.add_data(*row)

    if args.wandb:
        wandb.run.log({TABLE_NAME : grad_cam_table})



# def saliency_mals(args, model, x_test, y_test):

#from vis.visualization import visualize_saliency
#
#def get_feature_maps(model, layer_id, input_image):
#
#    model_ = tf.keras.models.Model(inputs=[model.inputs],
#                outputs=[model.layers[layer_id].output]
#    )
#    return model_.predict(np.expand_dims(input_image,
#                                         axis=0))[0,:,:,:].transpose((2,0,1))
#
#def plot_features_map(img_idx=None, layer_idx=[0, 2, 4, 6, 8, 10, 12, 16],
#                      x_test=x_test, ytest=ytest, cnn=cnn):
#    if img_idx == None:
#        img_idx = randint(0, ytest.shape[0])
#    input_image = x_test[img_idx]
#    fig, ax = plt.subplots(3,3,figsize=(10,10))
#    ax[0][0].imshow(input_image)
#    ax[0][0].set_title('original img id {} - {}'.format(img_idx,
#                                                        labels[ytest[img_idx][0]]))
#    for i, l in enumerate(layer_idx):
#        feature_map = get_feature_maps(cnn, l, input_image)
#        ax[(i+1)//3][(i+1)%3].imshow(feature_map[:,:,0])
#        ax[(i+1)//3][(i+1)%3].set_title('layer {} - {}'.format(l,
#                                                               cnn.layers[l].get_config()['name']))
#    return img_idx
#
#def plot_saliency(img_idx=None):
#    img_idx = plot_features_map(img_idx)
#
#    grads = visualize_saliency(cnn_saliency, -1, filter_indices=ytest[img_idx][0],
#                               seed_input=x_test[img_idx], backprop_modifier=None,
#                               grad_modifier="absolute")
#
#    predicted_label = labels[np.argmax(cnn.predict(x_test[img_idx].reshape(1,32,32,3)),1)[0]]
#
#    fig, ax = plt.subplots(1,2, figsize=(10,5))
#    ax[0].imshow(x_test[img_idx])
#    ax[0].set_title(f'original img id {img_idx} - {labels[ytest[img_idx][0]]}')
#    ax[1].imshow(grads, cmap='jet')
#    ax[1].set_title(f'saliency - predicted {predicted_label}')


#def visualize_intermediate_activations(layer_names, activations):
#    assert len(layer_names)==len(activations), "Make sure layers and activation values match"
#    images_per_row=16
#
#    for layer_name, layer_activation in zip(layer_names, activations):
#        nb_features = layer_activation.shape[-1]
#        size= layer_activation.shape[1]
#
#        nb_cols = nb_features // images_per_row
#        grid = np.zeros((size*nb_cols, size*images_per_row))
#
#        for col in range(nb_cols):
#            for row in range(images_per_row):
#                feature_map = layer_activation[0,:,:,col*images_per_row + row]
#                feature_map -= feature_map.mean()
#                feature_map /= feature_map.std()
#                feature_map *=255
#                feature_map = np.clip(feature_map, 0, 255).astype(np.uint8)
#
#                grid[col*size:(col+1)*size, row*size:(row+1)*size] = feature_map
#
#        scale = 1./size
#        plt.figure(figsize=(scale*grid.shape[1], scale*grid.shape[0]))
#        plt.title(layer_name)
#        plt.grid(False)
#        plt.axis('off')
#        plt.imshow(grid, aspect='auto', cmap='viridis')
#    plt.show()
## select all the layers for which you want to visualize the outputs and store it in a list
#outputs = [layer.output for layer in model.layers[1:18]]
#
## Define a new model that generates the above output
#vis_model = Model(model.input, outputs)
#
## store the layer names we are interested in
#layer_names = []
#for layer in outputs:
#    layer_names.append(layer.name.split("/")[0])
#
#
#print("Layers that will be used for visualization: ")
#print(layer_names)
