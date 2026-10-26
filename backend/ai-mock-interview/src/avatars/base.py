# Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
# Based on LiveTalking (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking (Apache-2.0).

import math
import torch
import numpy as np

import subprocess
import os
import time
import cv2
import glob
import resampy
from datetime import datetime

import queue
from queue import Queue
from threading import Thread, Event
from io import BytesIO
import soundfile as sf

import asyncio
from av import AudioFrame, VideoFrame

import av
from fractions import Fraction

from src.tts.factory import create_tts_engine
from src.utils.logging import logger

from tqdm import tqdm


def read_imgs(img_list):
    frames = []
    logger.info('reading images...')
    for img_path in tqdm(img_list):
        frame = cv2.imread(img_path)
        frames.append(frame)
    return frames

def play_audio(quit_event,queue):        
    import pyaudio
    p = pyaudio.PyAudio()
    stream = p.open(
        rate=16000,
        channels=1,
        format=8,
        output=True,
        output_device_index=1,
    )
    stream.start_stream()
    while not quit_event.is_set():
        stream.write(queue.get(block=True))
    stream.close()

class BaseAvatar:
    def __init__(self, config):
        self.config = config
        self.sample_rate = 16000
        # 每个音频块对应一帧视频（例如 50fps 音频 -> 20ms 一个 chunk）
        self.chunk = self.sample_rate // config.audio.fps
        self.sessionid = self.config.sessionid

        # TTS 引擎负责把文本转成音频并推送到音频流
        self.tts = create_tts_engine(config.tts.type, config, self)
        self.speaking = False

        # 录制相关状态
        self.recording = False
        self._record_video_pipe = None
        self._record_audio_pipe = None
        self.width = self.height = 0
        self.current_record_file = None  # 当前录制的文件名

        # 自定义音视频循环播放相关
        self.curr_state=0
        self.custom_img_cycle = {}
        self.custom_audio_cycle = {}
        self.custom_audio_index = {}
        self.custom_index = {}
        self.custom_opt = {}
        self.__loadcustom()

    def put_msg_txt(self,msg,datainfo:dict={}):
        # 文本消息交给 TTS 处理
        self.tts.put_msg_txt(msg,datainfo)
    
    def put_audio_frame(self,audio_chunk,datainfo:dict={}): #16khz 20ms pcm
        # 直接把音频块推给音频流（用于 WebRTC / 录制）
        self.audio_stream.put_audio_frame(audio_chunk,datainfo)

    def put_audio_file(self,filebyte,datainfo:dict={}): 
        # 文件音频按 chunk 切片后送入音频流
        input_stream = BytesIO(filebyte)
        stream = self.__create_bytes_stream(input_stream)
        streamlen = stream.shape[0]
        idx=0
        while streamlen >= self.chunk:  #and self.state==State.RUNNING
            self.put_audio_frame(stream[idx:idx+self.chunk],datainfo)
            streamlen -= self.chunk
            idx += self.chunk
    
    def __create_bytes_stream(self,byte_stream):
        stream, sample_rate = sf.read(byte_stream) # [T*sample_rate,] float64
        logger.info(f'[INFO]put audio stream {sample_rate}: {stream.shape}')
        stream = stream.astype(np.float32)

        if stream.ndim > 1:
            logger.info(f'[WARN] audio has {stream.shape[1]} channels, only use the first.')
            stream = stream[:, 0]
    
        if sample_rate != self.sample_rate and stream.shape[0]>0:
            logger.info(f'[WARN] audio sample rate is {sample_rate}, resampling into {self.sample_rate}.')
            stream = resampy.resample(x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)

        return stream

    def flush_talk(self):
        # 清空 TTS 和音频流队列，快速打断当前发声
        self.tts.flush_talk()
        self.audio_stream.flush_talk()

    def is_speaking(self)->bool:
        return self.speaking
    
    def __loadcustom(self):
        # 读取自定义音视频素材（用于特殊动作/表情）
        for item in self.config.customopt:
            logger.info(item)
            input_img_list = glob.glob(os.path.join(item['imgpath'], '*.[jpJP][pnPN]*[gG]'))
            input_img_list = sorted(input_img_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
            self.custom_img_cycle[item['audiotype']] = read_imgs(input_img_list)
            self.custom_audio_cycle[item['audiotype']], sample_rate = sf.read(item['audiopath'], dtype='float32')
            self.custom_audio_index[item['audiotype']] = 0
            self.custom_index[item['audiotype']] = 0
            self.custom_opt[item['audiotype']] = item

    def init_customindex(self):
        self.curr_state=0
        for key in self.custom_audio_index:
            self.custom_audio_index[key]=0
        for key in self.custom_index:
            self.custom_index[key]=0

    def notify(self,eventpoint):
        logger.info("notify:%s",eventpoint)

    def mirror_index(self,size, index):
        # 通过镜像索引实现正反往返播放
        #size = len(self.coord_list_cycle)
        turn = index // size
        res = index % size
        if turn % 2 == 0:
            return res
        else:
            return size - res - 1 
    
    def get_audio_stream(self,audiotype):
        # 按 chunk 切片返回自定义音频片段
        idx = self.custom_audio_index[audiotype]
        stream = self.custom_audio_cycle[audiotype][idx:idx+self.chunk]
        self.custom_audio_index[audiotype] += self.chunk
        if self.custom_audio_index[audiotype]>=self.custom_audio_cycle[audiotype].shape[0]:
            self.curr_state = 1  #当前视频不循环播放，切换到静音状态
        return stream
    
    def set_custom_state(self,audiotype, reinit=True):
        print('set_custom_state:',audiotype)
        if self.custom_audio_index.get(audiotype) is None:
            return
        self.curr_state = audiotype
        if reinit:
            self.custom_audio_index[audiotype] = 0
            self.custom_index[audiotype] = 0

    def process_frames(self,quit_event,loop=None,audio_track=None,video_track=None):
        logger.info(f'[帧处理] process_frames 线程启动, sessionid={self.config.sessionid}')
        video_samples = 0
        last_video_samples = None
        last_video_mode = None
        idle_image = None
        while not quit_event.is_set():
            try:
                res_frame,idx,audio_frames = self.res_frame_queue.get(block=True, timeout=1)
            except queue.Empty:
                continue

            frame_samples = video_samples
            video_samples += sum(len(frame) for frame, _, _ in audio_frames)
            self.speaking = any(audio_type == 0 for _, audio_type, _ in audio_frames)
            audiotype = audio_frames[0][1]
            custom_video = not self.speaking and audiotype in self.custom_index
            video_mode = 'speech' if self.speaking else ('custom' if custom_video else 'idle')

            # Keep a single closed-mouth image while waiting for the candidate.
            # Publish immediately on each mode change, then only once per second
            # in idle mode. Audio and its event notifications remain continuous.
            send_video = (
                video_mode != 'idle'
                or last_video_mode != 'idle'
                or last_video_samples is None
                or frame_samples - last_video_samples >= self.sample_rate
            )
            combine_frame = None
            if send_video or self.recording:
                if self.speaking:
                    idle_image = None
                    try:
                        combine_frame = self.paste_back_frame(res_frame,idx)
                    except Exception as error:
                        logger.warning(f"paste_back_frame error: {error}")
                        combine_frame = self.frame_list_cycle[idx].copy()
                elif custom_video:
                    idle_image = None
                    mirindex = self.mirror_index(len(self.custom_img_cycle[audiotype]),self.custom_index[audiotype])
                    combine_frame = self.custom_img_cycle[audiotype][mirindex].copy()
                else:
                    if idle_image is None:
                        idle_image = self.frame_list_cycle[idx].copy()
                        cv2.putText(idle_image, "Linly-Talker-Stream", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (128,128,128), 1)
                    combine_frame = idle_image
                if video_mode != 'idle':
                    cv2.putText(combine_frame, "Linly-Talker-Stream", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (128,128,128), 1)

                if send_video:
                    new_frame = VideoFrame.from_ndarray(combine_frame, format="bgr24")
                    new_frame.pts = frame_samples
                    new_frame.time_base = Fraction(1, self.sample_rate)
                    asyncio.run_coroutine_threadsafe(video_track._queue.put((new_frame,None)), loop)
                    last_video_samples = frame_samples
                    last_video_mode = video_mode
                self.record_video_data(combine_frame)

            if custom_video:
                self.custom_index[audiotype] += 1

            for audio_frame in audio_frames:
                frame,audio_type,eventpoint = audio_frame
                frame = (frame * 32767).astype(np.int16)
                new_frame = AudioFrame(format='s16', layout='mono', samples=frame.shape[0])
                new_frame.planes[0].update(frame.tobytes())
                new_frame.sample_rate=16000
                asyncio.run_coroutine_threadsafe(audio_track._queue.put((new_frame,eventpoint)), loop)
                self.record_audio_data(frame)
        logger.info('basereal process_frames thread stop')


    def start_recording(self):
        """开始录制视频"""
        logger.info(f'[录制] start_recording 被调用, sessionid={self.config.sessionid}')
        logger.info(f'[录制] 当前 recording 状态: {self.recording}')
        logger.info(f'[录制] 当前视频尺寸: width={self.width}, height={self.height}')
        
        if self.recording:
            logger.warning(f'[录制] 已经在录制中，忽略本次调用')
            return

        # 等到首帧拿到真实尺寸后再启动 ffmpeg
        self.recording = True
        if self.width == 0 or self.height == 0:
            logger.info(f'[录制] 视频尺寸未初始化，将在第一帧数据到达时启动 ffmpeg 进程')
            return
        
        # 如果尺寸已知，立即启动 ffmpeg 进程
        self._init_recording_pipes()
    
    def _init_recording_pipes(self):
        """初始化录制管道（需要在 width/height 已知后调用）"""
        if self._record_video_pipe is not None:
            return  # 已经初始化过了
        
        logger.info(f'[录制] 初始化 ffmpeg 进程，视频尺寸: {self.width}x{self.height}')
        
        command = ['ffmpeg',
                    '-y', '-an',
                    '-f', 'rawvideo',
                    '-vcodec','rawvideo',
                    '-pix_fmt', 'bgr24', #像素格式
                    '-s', "{}x{}".format(self.width, self.height),
                    '-r', str(25),
                    '-i', '-',
                    '-pix_fmt', 'yuv420p', 
                    '-vcodec', "h264",
                    #'-f' , 'flv',                  
                    f'temp{self.config.sessionid}.mp4']
        logger.info(f'[录制] 启动视频录制进程: {" ".join(command)}')
        self._record_video_pipe = subprocess.Popen(command, shell=False, stdin=subprocess.PIPE)
        logger.info(f'[录制] 视频录制进程 PID: {self._record_video_pipe.pid}')

        acommand = ['ffmpeg',
                    '-y', '-vn',
                    '-f', 's16le',
                    #'-acodec','pcm_s16le',
                    '-ac', '1',
                    '-ar', '16000',
                    '-i', '-',
                    '-acodec', 'aac',
                    #'-f' , 'wav',                  
                    f'temp{self.config.sessionid}.aac']
        logger.info(f'[录制] 启动音频录制进程: {" ".join(acommand)}')
        self._record_audio_pipe = subprocess.Popen(acommand, shell=False, stdin=subprocess.PIPE)
        logger.info(f'[录制] 音频录制进程 PID: {self._record_audio_pipe.pid}')
        logger.info(f'[录制] ffmpeg 进程初始化完成')
    
    def record_video_data(self,image):
        # 首帧到来时写入真实尺寸
        if self.width == 0:
            print("image.shape:",image.shape)
            self.height,self.width,_ = image.shape
        if self.recording:
            self._record_video_pipe.stdin.write(image.tostring())

    def record_audio_data(self,frame):
        if self.recording:
            self._record_audio_pipe.stdin.write(frame.tostring())
    
    def stop_recording(self):
        """停止录制视频"""
        logger.info(f'[录制] stop_recording 被调用, sessionid={self.config.sessionid}')
        logger.info(f'[录制] 当前 recording 状态: {self.recording}')
        
        if not self.recording:
            logger.warning(f'[录制] 当前未在录制状态，忽略停止请求')
            return
        
        self.recording = False
        
        # 检查是否已经初始化了管道
        if self._record_video_pipe is None or self._record_audio_pipe is None:
            logger.warning(f'[录制] ffmpeg 进程未初始化（可能尚未收到第一帧数据），无法停止录制')
            return
        
        logger.info(f'[录制] 开始关闭录制进程...')
        
        try:
            self._record_video_pipe.stdin.close()
            logger.info(f'[录制] 视频管道已关闭，等待进程结束...')
            self._record_video_pipe.wait()
            logger.info(f'[录制] 视频录制进程已结束')
        except Exception as e:
            logger.error(f'[录制] 关闭视频录制进程失败: {e}')
        
        try:
            self._record_audio_pipe.stdin.close()
            logger.info(f'[录制] 音频管道已关闭，等待进程结束...')
            self._record_audio_pipe.wait()
            logger.info(f'[录制] 音频录制进程已结束')
        except Exception as e:
            logger.error(f'[录制] 关闭音频录制进程失败: {e}')
        
        # 重置管道
        self._record_video_pipe = None
        self._record_audio_pipe = None
        
        # 生成唯一文件名（带时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        records_dir = 'data/records'
        os.makedirs(records_dir, exist_ok=True)
        
        video_file = f'temp{self.config.sessionid}.mp4'
        audio_file = f'temp{self.config.sessionid}.aac'
        output_file = f'{records_dir}/record_{timestamp}_session{self.config.sessionid}.mp4'
        
        logger.info(f'[录制] 检查临时文件:')
        logger.info(f'[录制]   视频文件: {video_file}, 存在: {os.path.exists(video_file)}')
        if os.path.exists(video_file):
            logger.info(f'[录制]   视频文件大小: {os.path.getsize(video_file)} bytes')
        logger.info(f'[录制]   音频文件: {audio_file}, 存在: {os.path.exists(audio_file)}')
        if os.path.exists(audio_file):
            logger.info(f'[录制]   音频文件大小: {os.path.getsize(audio_file)} bytes')
        
        cmd_combine_audio = f"ffmpeg -y -i {audio_file} -i {video_file} -c:v copy -c:a copy {output_file}"
        logger.info(f'[录制] 合并音视频命令: {cmd_combine_audio}')
        result = os.system(cmd_combine_audio)
        logger.info(f'[录制] 合并命令返回值: {result}')
        
        if os.path.exists(output_file):
            logger.info(f'[录制] ✓ 录制完成! 输出文件: {output_file}, 大小: {os.path.getsize(output_file)} bytes')
            self.current_record_file = output_file  # 保存文件路径
        else:
            logger.error(f'[录制] ✗ 输出文件未生成: {output_file}')
            self.current_record_file = None
        
        # 清理临时文件
        try:
            if os.path.exists(video_file):
                os.remove(video_file)
                logger.info(f'[录制] 已删除临时视频文件: {video_file}')
            if os.path.exists(audio_file):
                os.remove(audio_file)
                logger.info(f'[录制] 已删除临时音频文件: {audio_file}')
        except Exception as e:
            logger.warning(f'[录制] 清理临时文件失败: {e}')
