/**
 * VivaVoce Audio Recording & Real-Time Waveform Visualizer
 * Uses MediaRecorder API and Web Audio API AnalyserNode
 */

class AudioRecorderManager {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.stream = null;
        this.audioContext = null;
        this.analyser = null;
        this.animFrameId = null;
        this.startTime = null;
        this.timerInterval = null;
        this.isRecording = false;
        this.onTimerUpdate = null;
    }

    getSupportedMimeType() {
        const types = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/mp4',
            'audio/aac'
        ];
        for (const t of types) {
            if (MediaRecorder.isTypeSupported(t)) {
                return t;
            }
        }
        return '';
    }

    async startRecording(canvasElement, onTimerTick) {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            const mimeType = this.getSupportedMimeType();
            const options = mimeType ? { mimeType } : {};
            this.mediaRecorder = new MediaRecorder(this.stream, options);
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.start(250); // Slice every 250ms
            this.isRecording = true;
            this.startTime = Date.now();

            // Setup timer
            if (onTimerTick) {
                this.onTimerUpdate = onTimerTick;
                this.timerInterval = setInterval(() => {
                    const elapsedSecs = Math.floor((Date.now() - this.startTime) / 1000);
                    const mins = String(Math.floor(elapsedSecs / 60)).padStart(2, '0');
                    const secs = String(elapsedSecs % 60).padStart(2, '0');
                    this.onTimerUpdate(`${mins}:${secs}`);
                }, 500);
            }

            // Setup Web Audio Visualizer
            if (canvasElement) {
                this.setupVisualizer(canvasElement);
            }

            return true;
        } catch (err) {
            console.error("Error accessing microphone:", err);
            throw err;
        }
    }

    setupVisualizer(canvas) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        this.audioContext = new AudioContextClass();
        const source = this.audioContext.createMediaStreamSource(this.stream);
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 128;
        source.connect(this.analyser);

        const canvasCtx = canvas.getContext('2d');
        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const draw = () => {
            if (!this.isRecording) return;
            this.animFrameId = requestAnimationFrame(draw);

            this.analyser.getByteFrequencyData(dataArray);

            const width = canvas.width;
            const height = canvas.height;

            canvasCtx.clearRect(0, 0, width, height);

            const barWidth = (width / bufferLength) * 2.2;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                const barHeight = (dataArray[i] / 255) * height * 0.9;

                // Gradient Celeste Marino (#0083B0 to #00B4DB)
                const gradient = canvasCtx.createLinearGradient(0, height, 0, height - barHeight);
                gradient.addColorStop(0, '#0083B0');
                gradient.addColorStop(1, '#00B4DB');

                canvasCtx.fillStyle = gradient;
                canvasCtx.beginPath();
                canvasCtx.roundRect(x, height - barHeight, barWidth - 2, barHeight, [4, 4, 0, 0]);
                canvasCtx.fill();

                x += barWidth;
            }
        };

        draw();
    }

    stopRecording() {
        return new Promise((resolve, reject) => {
            if (!this.mediaRecorder || this.mediaRecorder.state === 'inactive') {
                return reject(new Error("No active recording"));
            }

            this.mediaRecorder.onstop = () => {
                this.isRecording = false;
                if (this.timerInterval) clearInterval(this.timerInterval);
                if (this.animFrameId) cancelAnimationFrame(this.animFrameId);

                // Stop tracks
                if (this.stream) {
                    this.stream.getTracks().forEach(track => track.stop());
                }
                if (this.audioContext && this.audioContext.state !== 'closed') {
                    this.audioContext.close();
                }

                const mimeType = this.mediaRecorder.mimeType || 'audio/webm';
                const audioBlob = new Blob(this.audioChunks, { type: mimeType });
                resolve({ blob: audioBlob, mimeType });
            };

            this.mediaRecorder.stop();
        });
    }

    cancelRecording() {
        this.isRecording = false;
        if (this.timerInterval) clearInterval(this.timerInterval);
        if (this.animFrameId) cancelAnimationFrame(this.animFrameId);
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
        }
        if (this.audioContext && this.audioContext.state !== 'closed') {
            this.audioContext.close();
        }
    }
}

// Global recorder instance
window.vivaVoceAudio = new AudioRecorderManager();
