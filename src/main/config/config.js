import path from 'path'
import os from 'os'

const isWin = process.platform === 'win32'
const winDataRoot = process.env.DUIX_DATA_ROOT_WIN || path.join('C:', 'duix_avatar_data')
const unixDataRoot = path.join(os.homedir(), 'duix_avatar_data')
const dataRoot = isWin ? winDataRoot : unixDataRoot

export const serviceUrl = {
  face2face: process.env.DUIX_FACE2FACE_BASE_URL || 'http://127.0.0.1:8383/easy',
  tts: process.env.DUIX_TTS_BASE_URL || 'http://127.0.0.1:18180'
}

export const assetPath = {
  model: path.join(dataRoot, 'face2face', 'temp'), // 模特视频
  ttsProduct: path.join(dataRoot, 'face2face', 'temp'), // TTS 产物
  ttsRoot: path.join(dataRoot, 'voice', 'data'), // TTS服务根目录
  ttsTrain: path.join(dataRoot, 'voice', 'data', 'origin_audio') // TTS 训练产物
}
