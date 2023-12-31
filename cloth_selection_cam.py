import streamlit as st
#基本ライブラリ
import numpy as np
import pandas as pd

from PIL import Image

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
from torchvision import transforms
from torchvision import datasets
from torchvision.utils import make_grid
import pytorch_lightning as pl
import torchmetrics
from torchmetrics.functional import accuracy
import torchsummary
from torchsummary import summary
from pytorch_lightning.loggers import CSVLogger

from torchvision.models import resnet18

from torch.utils.data import Dataset

#Grad-Cam用のライブラリをインポート
import gradcam
from gradcam.utils import visualize_cam
from gradcam import GradCAM, GradCAMpp  #GradCAMとGradCaM++の比較のため両方インポート

#予測モデル構築
class Net(pl.LightningModule):
    
  def __init__(self):
    super().__init__()

    self.feature = resnet18(pretrained=True)

    self.fc = nn.Linear(1000, 2)

  def forward(self, x):
    h = self.feature(x)
    h = self.fc(h)
    return h

  def training_step(self, batch, batch_idx):
    x, t = batch
    y = self(x)
    loss = F.cross_entropy(y, t)
    self.log('train_loss', loss, on_step=True, on_epoch=True)
    self.log('train_acc', accuracy(y.softmax(dim=-1), t, task='multiclass', num_classes=2), on_step=True, on_epoch=True)
    return loss

  def validation_step(self, batch, batch_idx):
    x, t = batch
    y = self(x)
    loss = F.cross_entropy(y, t)
    self.log('val_loss', loss, on_step=False, on_epoch=True)
    self.log('val_acc', accuracy(y.softmax(dim=-1), t, task='multiclass', num_classes=2), on_step=False, on_epoch=True)
    return loss

  def test_step(self, batch, batch_idx):
    x, t = batch
    y = self(x)
    loss = F.cross_entropy(y, t)
    self.log('test_loss', loss, on_step=False, on_epoch=True)
    self.log('test_acc', accuracy(y.softmax(dim=-1), t, task='multiclass', num_classes=2), on_step=False, on_epoch=True)
    return loss

  def configure_optimizers(self):
    optimizer = torch.optim.SGD(self.parameters(), lr=0.01)
    return optimizer

#予測用の入力画像前処理コード
#データの前処理 学習時と同じ前処理を施す。
def preprocess_image(image):
    transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    
    image = transform(image).unsqueeze(0)
    return image

#Gard-Camで重ねる画像の前処理(backgraund画像の前処理)
def preprocess_image_bg(image):
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
    ])
    
    image_bg = transform(image)
    return image_bg

#アップロード画像を(224, 224)にリサイズする前処理（Grad-CAMのヒートマップ画像と同じサイズで並べて表示するために)
def preprocess_image_resize(image):
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
    ])
    
    image_resized = transform(image)
    return image_resized

#ネットワークの準備
net = Net().cpu().eval()
#重みの読み込み
net.load_state_dict(torch.load('cloth_selection.pt', map_location=torch.device('cpu')))

#streamlitアプリのメインコード
def main():
    st.title('Tシャツの好みを出力するアプリ')
    
    uploaded_image = st.file_uploader('Tシャツの画像をアップロードしてください', type=['jpg', 'jpeg', 'png'])
    
    if uploaded_image is not None:
        image = Image.open(uploaded_image)
        
        #アップロード画像を表示用にリサイズして表示
        uploaded_image_show = preprocess_image_resize(image)
        st.image(uploaded_image_show, caption='Uploaded Image', use_column_width=True)
        
        #Grad-Camで重ねるバックグラウンドイメージも用意する
        cam_img = preprocess_image_bg(image)
        
        #予測ボタンが押されたら予測を実行
        if st.button('予測'):
            #画像を前処理
            preprocessed_image = preprocess_image(image)
            
            #モデルに画像を入力して予測
            if net is not None:
                with torch.no_grad():
                    
                    #予測
                    y_pred = net(preprocessed_image)

                    #確率値に変換
                    y_pred = F.softmax(y_pred)
                    
                    #最大値のラベルを取得
                    y_pred_label = torch.argmax(y_pred)
                    
                    #予測結果を表示
                    if y_pred_label == 0:
                        st.write('予測結果：すみません。このTシャツは好みではないです。')
                    else:
                        st.write('予測結果：このTシャツは好みです。')
                    
                #Grad-Cam
                if y_pred_label is not None:
                    #特徴抽出器の最後の層をtarget_layerに渡す
                    target_layer = net.feature.layer4[-1]
                    
                    #インスタンス化
                    #gradcam = GradCAM(net, target_layer)  #Grad-CAMは非表示とする
                    gradcam_pp= GradCAMpp(net, target_layer)
                    #最初の出力だけ取得
                    
                    #mask, _ =gradcam(preprocessed_image)　　#Grad-CAMは非表示とする
                    #heatmap, result = visualize_cam(mask, cam_img)　　#Grad-CAMは非表示とする
                    
                    mask_pp, _ = gradcam_pp(preprocessed_image)
                    heatmap_pp, result_pp = visualize_cam(mask_pp, cam_img)
                    
                    images = []
                    images.extend([cam_img, result_pp])
                    
                    grid_image = make_grid(images, nrow=2)
                    
                    st.image(transforms.ToPILImage()(grid_image), caption="Grad-CAM Results", use_column_width=True)
                    
                    
if __name__ == '__main__':
    main()