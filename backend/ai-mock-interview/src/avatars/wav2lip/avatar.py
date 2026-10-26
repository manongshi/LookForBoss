# Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
# Based on LiveTalking (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking (Apache-2.0).

import math
import torch
import numpy as np

#from .utils import *
import os
import time
import cv2
import glob
import pickle
import copy
import json
from pathlib import Path

import queue
from queue import Queue
from threading import Thread, Event
import torch.multiprocessing as mp


from src.avatars.wav2lip.audio_stream_handler import LipAudioStreamHandler
import asyncio
from av import AudioFrame, VideoFrame
from src.avatars.wav2lip.models import Wav2Lip
from src.avatars.base import BaseAvatar

#from imgcache import ImgCache

from tqdm import tqdm
from src.utils.logging import logger

device = "cuda" if torch.cuda.is_available() else ("mps" if (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()) else "cpu")
print('Using {} for inference.'.format(device))

def _load(checkpoint_path):
	if device == 'cuda':
		checkpoint = torch.load(checkpoint_path) #,weights_only=True
	else:
		checkpoint = torch.load(checkpoint_path,
								map_location=lambda storage, loc: storage)
	return checkpoint

def load_model(path):
	model = Wav2Lip()
	logger.info("Load checkpoint from: {}".format(path))
	checkpoint = _load(path)
	s = checkpoint["state_dict"]
	new_s = {}
	for k, v in s.items():
		new_s[k.replace('module.', '')] = v
	model.load_state_dict(new_s)

	model = model.to(device)
	return model.eval()

def load_avatar(avatar_id):
    avatar_path = f"./data/avatars/{avatar_id}"
    full_imgs_path = f"{avatar_path}/full_imgs" 
    face_imgs_path = f"{avatar_path}/face_imgs" 
    coords_path = f"{avatar_path}/coords.pkl"

    if not os.path.isfile(coords_path):
        source_dir = Path(__file__).resolve().parents[3] / "assets/avatars"
        source_path = source_dir / f"{avatar_id}.png"
        metadata_path = source_dir / f"{avatar_id}.json"
        if not source_path.is_file() or not metadata_path.is_file():
            raise FileNotFoundError(f"Avatar assets not found: {avatar_id}")
        frame = cv2.imread(str(source_path))
        if frame is None:
            raise ValueError('面试官图片无法读取，请重新准备人物素材。')
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        y1, y2, x1, x2 = metadata['face_bounds']
        height, width = frame.shape[:2]
        if not (0 <= y1 < y2 <= height and 0 <= x1 < x2 <= width):
            raise ValueError('面试官人脸位置超出图片范围，请重新准备人物素材。')
        face = cv2.resize(frame[y1:y2, x1:x2], (256, 256))
        return [frame], [face], [(y1, y2, x1, x2)]
    
    with open(coords_path, 'rb') as f:
        coord_list_cycle = pickle.load(f)
    input_img_list = glob.glob(os.path.join(full_imgs_path, '*.[jpJP][pnPN]*[gG]'))
    input_img_list = sorted(input_img_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    frame_list_cycle = read_imgs(input_img_list)
    #self.imagecache = ImgCache(len(self.coord_list_cycle),self.full_imgs_path,1000)
    input_face_list = glob.glob(os.path.join(face_imgs_path, '*.[jpJP][pnPN]*[gG]'))
    input_face_list = sorted(input_face_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    face_list_cycle = read_imgs(input_face_list)

    return frame_list_cycle,face_list_cycle,coord_list_cycle

@torch.no_grad()
def warm_up(batch_size,model,modelres):
    # 预热函数
    logger.info('warmup model...')
    img_batch = torch.ones(batch_size, 6, modelres, modelres).to(device)
    mel_batch = torch.ones(batch_size, 1, 80, 16).to(device)
    model(mel_batch, img_batch)

def read_imgs(img_list):
    frames = []
    logger.info('reading images...')
    for img_path in tqdm(img_list):
        frame = cv2.imread(img_path)
        frames.append(frame)
    return frames

def __mirror_index(size, index):
    #size = len(self.coord_list_cycle)
    turn = index // size
    res = index % size
    if turn % 2 == 0:
        return res
    else:
        return size - res - 1 

def inference(quit_event,batch_size,face_list_cycle,audio_feat_queue,audio_out_queue,res_frame_queue,model):
    
    #model = load_model("./models/wav2lip.pth")
    # input_face_list = glob.glob(os.path.join(face_imgs_path, '*.[jpJP][pnPN]*[gG]'))
    # input_face_list = sorted(input_face_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    # face_list_cycle = read_imgs(input_face_list)
    
    #input_latent_list_cycle = torch.load(latents_out_path)
    length = len(face_list_cycle)
    index = 0
    count=0
    counttime=0
    logger.info('start inference')
    while not quit_event.is_set():
        starttime=time.perf_counter()
        mel_batch = []
        try:
            mel_batch = audio_feat_queue.get(block=True, timeout=1)
        except queue.Empty:
            continue
            
        is_all_silence=True
        audio_frames = []
        for _ in range(batch_size*2):
            frame,type,eventpoint = audio_out_queue.get()
            audio_frames.append((frame,type,eventpoint))
            if type==0:
                is_all_silence=False

        if is_all_silence:
            for i in range(batch_size):
                res_frame_queue.put((None,__mirror_index(length,index),audio_frames[i*2:i*2+2]))
                index = index + 1
        else:
            # print('infer=======')
            t=time.perf_counter()
            img_batch = []
            for i in range(batch_size):
                idx = __mirror_index(length,index+i)
                face = face_list_cycle[idx]
                img_batch.append(face)
            img_batch, mel_batch = np.asarray(img_batch), np.asarray(mel_batch)

            img_masked = img_batch.copy()
            img_masked[:, face.shape[0]//2:] = 0

            img_batch = np.concatenate((img_masked, img_batch), axis=3) / 255.
            mel_batch = np.reshape(mel_batch, [len(mel_batch), mel_batch.shape[1], mel_batch.shape[2], 1])
            
            img_batch = torch.FloatTensor(np.transpose(img_batch, (0, 3, 1, 2))).to(device)
            mel_batch = torch.FloatTensor(np.transpose(mel_batch, (0, 3, 1, 2))).to(device)

            with torch.no_grad():
                pred = model(mel_batch, img_batch)
            pred = pred.cpu().numpy().transpose(0, 2, 3, 1) * 255.

            counttime += (time.perf_counter() - t)
            count += batch_size
            #_totalframe += 1
            if count>=100:
                logger.info(f"------actual avg infer fps:{count/counttime:.4f}")
                count=0
                counttime=0
            for i,res_frame in enumerate(pred):
                #self.__pushmedia(res_frame,loop,audio_track,video_track)
                res_frame_queue.put((res_frame,__mirror_index(length,index),audio_frames[i*2:i*2+2]))
                index = index + 1
            #print('total batch time:',time.perf_counter()-starttime)            
    logger.info('lipreal inference processor stop')

class Wav2LipAvatar(BaseAvatar):
    @torch.no_grad()
    def __init__(self, config, model, avatar):
        super().__init__(config)
        #self.opt = opt # shared with the trainer's opt to support in-place modification of rendering parameters.
        # self.W = opt.W
        # self.H = opt.H

        self.fps = config.audio.fps # 20 ms per frame
        
        self.batch_size = config.model.batch_size
        self.idx = 0
        self.res_frame_queue = Queue(self.batch_size*2)  #mp.Queue
        #self.__loadavatar()
        self.model = model
        self.frame_list_cycle,self.face_list_cycle,self.coord_list_cycle = avatar

        self.audio_stream = LipAudioStreamHandler(config, self)
        self.audio_stream.warm_up()
        
        self.render_event = mp.Event()
    
    # def __del__(self):
    #     logger.info(f'lipreal({self.sessionid}) delete')

    def paste_back_frame(self,pred_frame,idx:int):
        bbox = self.coord_list_cycle[idx]
        combine_frame = copy.deepcopy(self.frame_list_cycle[idx])
        #combine_frame = copy.deepcopy(self.imagecache.get_img(idx))
        y1, y2, x1, x2 = bbox
        res_frame = cv2.resize(pred_frame.astype(np.uint8),(x2-x1,y2-y1))
        #combine_frame = get_image(ori_frame,res_frame,bbox)
        #t=time.perf_counter()
        combine_frame[y1:y2, x1:x2] = res_frame
        return combine_frame
            
    def render(self,quit_event,loop=None,audio_track=None,video_track=None):
        #if self.opt.asr:
        #     self.audio_stream.warm_up()

        self.init_customindex()
        self.tts.render(quit_event)
        
        infer_quit_event = Event()
        infer_thread = Thread(target=inference, args=(infer_quit_event,self.batch_size,self.face_list_cycle,
                                           self.audio_stream.feat_queue,self.audio_stream.output_queue,self.res_frame_queue,
                                           self.model,))  #mp.Process
        infer_thread.start()
        
        process_quit_event = Event()
        process_thread = Thread(target=self.process_frames, args=(process_quit_event,loop,audio_track,video_track))
        process_thread.start()

        #self.render_event.set() #start infer process render
        # Pace production by audio duration. Idle video is deliberately sparse,
        # so video queue depth no longer represents the media clock.
        batch_duration = self.batch_size * 2 / self.fps
        next_batch_at = time.monotonic()
        while not quit_event.is_set(): 
            self.audio_stream.run_step()
            next_batch_at += batch_duration
            remaining = next_batch_at - time.monotonic()
            if remaining > 0:
                quit_event.wait(remaining)
            else:
                # Do not generate a burst of old frames after a slow batch.
                next_batch_at = time.monotonic()
        #self.render_event.clear() #end infer process render
        logger.info('lipreal thread stop')

        infer_quit_event.set()
        infer_thread.join()

        process_quit_event.set()
        process_thread.join()
            
