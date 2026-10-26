"""音频流处理器基类 - 用于音频特征提取和缓冲管理"""
import time
import numpy as np

import queue
from queue import Queue
import torch.multiprocessing as mp

from src.avatars.base import BaseAvatar


class BaseAudioStreamHandler:
    """音频流处理器基类
    
    负责音频缓冲管理、音频帧处理和特征提取的基础框架。
    各 Avatar 模型应继承此类并实现 run_step() 方法。
    """
    def __init__(self, config, parent: BaseAvatar = None):
        self.config = config
        self.parent = parent

        # 20ms per frame (50fps audio)
        self.fps = config.audio.fps
        self.sample_rate = 16000
        self.chunk = self.sample_rate // self.fps
        self.queue = Queue()
        # 渲染侧消费的音频输出队列
        self.output_queue = mp.Queue()

        self.batch_size = config.model.batch_size

        self.frames = []
        self.frame_types = []
        self.stride_left_size = config.audio.l
        self.stride_right_size = config.audio.r
        #self.context_size = 10
        self.feat_queue = mp.Queue(2)

        #self.warm_up()

    def flush_talk(self):
        self.queue.queue.clear()

    def put_audio_frame(self, audio_chunk, datainfo: dict):
        self.queue.put((audio_chunk, datainfo))

    def get_audio_frame(self):        
        try:
            frame, eventpoint = self.queue.get(block=True, timeout=0.01)
            type = 0
            #print(f'[INFO] get frame {frame.shape}')
        except queue.Empty:
            if self.parent and self.parent.curr_state > 1: #播放自定义音频
                frame = self.parent.get_audio_stream(self.parent.curr_state)
                type = self.parent.curr_state
            else:
                frame = np.zeros(self.chunk, dtype=np.float32)
                type = 1
            eventpoint = None

        return frame, type, eventpoint 

    def get_audio_out(self): 
        return self.output_queue.get()
    
    def warm_up(self):
        for _ in range(self.stride_left_size + self.stride_right_size):
            audio_frame, type, eventpoint = self.get_audio_frame()
            self.frames.append(audio_frame)
            self.frame_types.append(type)
            self.output_queue.put((audio_frame, type, eventpoint))
        for _ in range(self.stride_left_size):
            self.output_queue.get()

    def run_step(self):
        """执行一步音频处理，子类需要实现此方法"""
        pass

    def get_next_feat(self, block, timeout):        
        return self.feat_queue.get(block, timeout)
