// Meet Transcriber Web UI

class TranscriberApp {
    constructor() {
        this.pollingIntervals = new Map();
        this.init();
    }

    init() {
        this.cacheElements();
        this.bindEvents();
        this.loadTheme();
    }

    cacheElements() {
        this.uploadArea = document.getElementById('uploadArea');
        this.fileInput = document.getElementById('fileInput');
        this.messagesContainer = document.getElementById('messages');
        this.welcomeScreen = document.getElementById('welcomeScreen');
        this.themeToggle = document.getElementById('themeToggle');
        this.optionsToggle = document.getElementById('optionsToggle');
        this.optionsContent = document.getElementById('optionsContent');
        this.enableDiarization = document.getElementById('enableDiarization');
        this.speakersGroup = document.getElementById('speakersGroup');
        this.chatContainer = document.getElementById('chatContainer');
    }

    bindEvents() {
        // File upload events
        this.uploadArea.addEventListener('click', () => this.fileInput.click());
        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));

        // Drag and drop
        this.uploadArea.addEventListener('dragover', (e) => this.handleDragOver(e));
        this.uploadArea.addEventListener('dragleave', (e) => this.handleDragLeave(e));
        this.uploadArea.addEventListener('drop', (e) => this.handleDrop(e));

        // Theme toggle
        this.themeToggle.addEventListener('click', () => this.toggleTheme());

        // Options panel
        this.optionsToggle.addEventListener('click', () => this.toggleOptions());

        // Diarization checkbox
        this.enableDiarization.addEventListener('change', () => this.toggleSpeakersGroup());
    }

    // Theme Management
    loadTheme() {
        const savedTheme = localStorage.getItem('theme') ||
            (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        document.documentElement.setAttribute('data-theme', savedTheme);
    }

    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
    }

    // Options Panel
    toggleOptions() {
        this.optionsContent.classList.toggle('open');
    }

    toggleSpeakersGroup() {
        this.speakersGroup.style.display = this.enableDiarization.checked ? 'flex' : 'none';
    }

    // Drag and Drop Handlers
    handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        this.uploadArea.classList.add('drag-over');
    }

    handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        this.uploadArea.classList.remove('drag-over');
    }

    handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        this.uploadArea.classList.remove('drag-over');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            this.uploadFile(files[0]);
        }
    }

    handleFileSelect(e) {
        const file = e.target.files[0];
        if (file) {
            this.uploadFile(file);
        }
        // Reset input so same file can be selected again
        this.fileInput.value = '';
    }

    // File Upload
    async uploadFile(file) {
        // Validate file type
        const validExtensions = ['.wav', '.mp3', '.m4a', '.flac', '.ogg', '.webm', '.wma', '.aac'];
        const fileExt = '.' + file.name.split('.').pop().toLowerCase();

        if (!validExtensions.includes(fileExt)) {
            this.showError('Unsupported file format. Please use: WAV, MP3, M4A, FLAC, OGG, WebM, WMA, or AAC.');
            return;
        }

        // Hide welcome screen
        this.welcomeScreen.classList.add('hidden');

        // Create message element
        const messageId = this.createMessageElement(file.name);

        // Build form data
        const formData = new FormData();
        formData.append('file', file);

        // Add options
        const language = document.getElementById('languageSelect').value;
        if (language) formData.append('language', language);

        const enableDiarization = document.getElementById('enableDiarization').checked;
        formData.append('enable_diarization', enableDiarization);

        if (enableDiarization) {
            const minSpeakers = document.getElementById('minSpeakers').value;
            const maxSpeakers = document.getElementById('maxSpeakers').value;
            if (minSpeakers) formData.append('min_speakers', parseInt(minSpeakers));
            if (maxSpeakers) formData.append('max_speakers', parseInt(maxSpeakers));
        }

        try {
            // Upload file
            const response = await fetch('/transcribe', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Upload failed');
            }

            const data = await response.json();

            // Start polling for status
            this.startPolling(data.job_id, messageId);

        } catch (error) {
            this.showErrorInMessage(messageId, error.message);
        }
    }

    // Message Element Creation
    createMessageElement(fileName) {
        const template = document.getElementById('messageTemplate');
        const clone = template.content.cloneNode(true);

        const messageId = 'msg-' + Date.now();
        const messageEl = clone.querySelector('.message');
        messageEl.id = messageId;

        // Set file name and timestamp
        clone.querySelector('.file-name').textContent = fileName;
        clone.querySelector('.timestamp').textContent = this.formatTime(new Date());

        // Add progress section
        const progressTemplate = document.getElementById('progressTemplate');
        const progressClone = progressTemplate.content.cloneNode(true);
        progressClone.querySelector('.progress-status').textContent = 'Uploading...';
        progressClone.querySelector('.progress-percent').textContent = '0%';

        clone.querySelector('.message-content').appendChild(progressClone);

        this.messagesContainer.appendChild(clone);

        // Scroll to bottom
        this.scrollToBottom();

        return messageId;
    }

    // Polling for Job Status
    startPolling(jobId, messageId) {
        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/transcribe/${jobId}`);
                const data = await response.json();

                this.updateProgress(messageId, data);

                if (data.status === 'completed') {
                    clearInterval(pollInterval);
                    this.pollingIntervals.delete(messageId);
                    this.showResult(messageId, jobId, data);
                } else if (data.status === 'failed') {
                    clearInterval(pollInterval);
                    this.pollingIntervals.delete(messageId);
                    this.showErrorInMessage(messageId, data.error || 'Transcription failed');
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        }, 1000);

        this.pollingIntervals.set(messageId, pollInterval);
    }

    updateProgress(messageId, data) {
        const messageEl = document.getElementById(messageId);
        if (!messageEl) return;

        const progressStatus = messageEl.querySelector('.progress-status');
        const progressPercent = messageEl.querySelector('.progress-percent');
        const progressFill = messageEl.querySelector('.progress-fill');

        if (progressStatus) {
            progressStatus.textContent = this.getStatusMessage(data.status, data.progress);
        }
        if (progressPercent) {
            progressPercent.textContent = `${Math.round(data.progress || 0)}%`;
        }
        if (progressFill) {
            progressFill.style.width = `${data.progress || 0}%`;
        }
    }

    getStatusMessage(status, progress) {
        if (status === 'pending') {
            return 'Waiting in queue';
        } else if (status === 'processing') {
            if (progress < 10) return 'Preparing audio';
            if (progress < 30) return 'Processing audio';
            if (progress < 70) return 'Transcribing';
            if (progress < 90) return 'Identifying speakers';
            return 'Finalizing';
        }
        return 'Processing';
    }

    // Show Result
    showResult(messageId, jobId, data) {
        const messageEl = document.getElementById(messageId);
        if (!messageEl) return;

        const messageContent = messageEl.querySelector('.message-content');
        messageContent.innerHTML = '';

        const resultTemplate = document.getElementById('resultTemplate');
        const clone = resultTemplate.content.cloneNode(true);

        // Fill metadata
        clone.querySelector('.duration').textContent = this.formatDuration(data.duration_seconds);
        clone.querySelector('.language').textContent = this.getLanguageName(data.language);
        clone.querySelector('.speakers').textContent = `${data.speakers?.length || 0} speaker${data.speakers?.length !== 1 ? 's' : ''}`;

        // Add download handlers
        clone.querySelector('.download-srt').addEventListener('click', () => this.downloadFile(jobId, 'srt'));
        clone.querySelector('.download-vtt').addEventListener('click', () => this.downloadFile(jobId, 'vtt'));
        clone.querySelector('.copy-btn').addEventListener('click', (e) => this.copyTranscript(e, data.segments));

        // Build transcript segments
        const segmentsContainer = clone.querySelector('.transcript-segments');
        this.buildTranscriptSegments(segmentsContainer, data.segments, data.speakers);

        messageContent.appendChild(clone);
        this.scrollToBottom();
    }

    buildTranscriptSegments(container, segments, speakers) {
        if (!segments || segments.length === 0) {
            container.innerHTML = '<p style="color: var(--text-tertiary); text-align: center; padding: 20px;">No transcript segments available.</p>';
            return;
        }

        // Create speaker color map
        const speakerColorMap = {};
        (speakers || []).forEach((speaker, index) => {
            speakerColorMap[speaker] = index % 8;
        });

        segments.forEach(segment => {
            const segmentEl = document.createElement('div');
            segmentEl.className = 'transcript-segment';

            const colorIndex = speakerColorMap[segment.speaker] ?? 0;

            segmentEl.innerHTML = `
                <div class="segment-header">
                    <span class="speaker-badge speaker-${colorIndex}">${this.formatSpeakerName(segment.speaker)}</span>
                    <span class="segment-time">${this.formatTimestamp(segment.start)} - ${this.formatTimestamp(segment.end)}</span>
                </div>
                <p class="segment-text">${this.escapeHtml(segment.text)}</p>
            `;

            container.appendChild(segmentEl);
        });
    }

    // Error Handling
    showError(message) {
        // Create a temporary error toast
        const toast = document.createElement('div');
        toast.className = 'error-toast';
        toast.style.cssText = `
            position: fixed;
            bottom: 180px;
            left: 50%;
            transform: translateX(-50%);
            background: var(--error-color);
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 0.875rem;
            z-index: 1000;
            animation: slideIn 0.3s ease;
        `;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => toast.remove(), 5000);
    }

    showErrorInMessage(messageId, message) {
        const messageEl = document.getElementById(messageId);
        if (!messageEl) return;

        const messageContent = messageEl.querySelector('.message-content');
        messageContent.innerHTML = '';

        const errorTemplate = document.getElementById('errorTemplate');
        const clone = errorTemplate.content.cloneNode(true);
        clone.querySelector('.error-message').textContent = message;

        messageContent.appendChild(clone);
    }

    // Download Handlers
    async downloadFile(jobId, format) {
        try {
            const response = await fetch(`/transcribe/${jobId}/download?format=${format}`);

            if (!response.ok) {
                throw new Error('Download failed');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `transcript.${format}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        } catch (error) {
            this.showError('Failed to download file: ' + error.message);
        }
    }

    async copyTranscript(event, segments) {
        const button = event.currentTarget;

        if (!segments || segments.length === 0) {
            this.showError('No transcript to copy');
            return;
        }

        const text = segments.map(s => `[${this.formatSpeakerName(s.speaker)}] ${s.text}`).join('\n\n');

        try {
            await navigator.clipboard.writeText(text);
            button.classList.add('copied');
            button.querySelector('span').textContent = 'Copied!';

            setTimeout(() => {
                button.classList.remove('copied');
                button.querySelector('span').textContent = 'Copy';
            }, 2000);
        } catch (error) {
            this.showError('Failed to copy to clipboard');
        }
    }

    // Utility Functions
    formatTime(date) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    formatDuration(seconds) {
        if (!seconds) return '0:00';

        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }

    formatTimestamp(seconds) {
        if (seconds === undefined || seconds === null) return '0:00';

        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }

    formatSpeakerName(speaker) {
        if (!speaker) return 'Unknown';
        // Convert SPEAKER_00 to Speaker 1
        const match = speaker.match(/SPEAKER_(\d+)/i);
        if (match) {
            return `Speaker ${parseInt(match[1]) + 1}`;
        }
        return speaker;
    }

    getLanguageName(code) {
        const languages = {
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'it': 'Italian',
            'pt': 'Portuguese',
            'nl': 'Dutch',
            'pl': 'Polish',
            'ru': 'Russian',
            'zh': 'Chinese',
            'ja': 'Japanese',
            'ko': 'Korean',
            'ar': 'Arabic',
            'hi': 'Hindi'
        };
        return languages[code] || code || 'Unknown';
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    scrollToBottom() {
        setTimeout(() => {
            this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
        }, 100);
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new TranscriberApp();
});
