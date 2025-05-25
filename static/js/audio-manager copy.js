class AudioManager {
    constructor() {
        this.backgroundMusic = null;
        this.currentAmbientSound = null;
        this.audioVolume = 0.3;
        this.isMuted = localStorage.getItem('audioMuted') === 'true';
        console.log('AudioManager: Initializing, isMuted:', this.isMuted);
        this.initAudio();
    }

    initAudio() {
        if (!this.backgroundMusic) {
            this.backgroundMusic = new Audio();
            this.backgroundMusic.loop = true;
            this.backgroundMusic.volume = this.isMuted ? 0 : this.audioVolume;
            console.log('AudioManager: Audio element created', this.backgroundMusic);
            this.createAudioControls();
        }
    }

    createAudioControls() {
        console.log('AudioManager: Creating audio controls');
        const audioControlsHTML = `
            <div id="audioControls" class="position-fixed bottom-0 end-0 p-3 audio-controls">
                <div class="btn-group">
                    <button id="toggleMusicBtn" class="btn btn-sm btn-outline-secondary">
                        <i class="bi bi-volume-${this.isMuted ? 'mute' : 'up'}"></i>
                    </button>
                    <button id="musicVolumeBtn" class="btn btn-sm btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown">
                        Volume
                    </button>
                    <div class="dropdown-menu p-2 dropdown-menu-end">
                        <input type="range" id="volumeSlider" class="form-range" min="0" max="100" value="${this.audioVolume * 100}">
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', audioControlsHTML);
        document.getElementById('toggleMusicBtn').addEventListener('click', () => this.toggleMute());
        document.getElementById('volumeSlider').addEventListener('input', (e) => this.setVolume(e.target.value / 100));
        console.log('AudioManager: Audio controls added');
    }

    toggleMute() {
        this.isMuted = !this.isMuted;
        this.backgroundMusic.volume = this.isMuted ? 0 : this.audioVolume;
        localStorage.setItem('audioMuted', this.isMuted);
        const muteButton = document.getElementById('toggleMusicBtn');
        if (muteButton) {
            muteButton.innerHTML = this.isMuted ? 
                '<i class="bi bi-volume-mute"></i>' : 
                '<i class="bi bi-volume-up"></i>';
        }
        console.log('AudioManager: Mute toggled, isMuted:', this.isMuted);
    }

    setVolume(volume) {
        this.audioVolume = volume;
        if (!this.isMuted) {
            this.backgroundMusic.volume = volume;
        }
        console.log('AudioManager: Volume set to', volume);
    }

    playAmbientSound(ambientSound, musicPath) {
        console.log('AudioManager: Attempting to play ambient sound:', ambientSound, 'at', musicPath);
        if (this.currentAmbientSound === ambientSound && this.backgroundMusic.src === musicPath) {
            console.log('AudioManager: Ambient sound and source unchanged, updating volume only');
            this.backgroundMusic.volume = this.isMuted ? 0 : this.audioVolume;
            return;
        }
        
        this.currentAmbientSound = ambientSound;
        this.backgroundMusic.src = musicPath;
        
        if (this.isMuted) {
            console.log('AudioManager: Audio is muted, setting volume to 0');
            this.backgroundMusic.volume = 0;
            return;
        }

        this.backgroundMusic.muted = true;
        const playPromise = this.backgroundMusic.play();
        
        if (playPromise !== undefined) {
            playPromise
                .then(() => {
                    console.log('AudioManager: Muted autoplay started successfully');
                    setTimeout(() => {
                        if (!this.isMuted) {
                            this.backgroundMusic.muted = false;
                            this.backgroundMusic.volume = this.audioVolume;
                            console.log('AudioManager: Audio unmuted');
                        } else {
                            this.backgroundMusic.volume = 0;
                            console.log('AudioManager: Audio remains muted');
                        }
                    }, 1000);
                })
                .catch(error => {
                    console.warn('AudioManager: Autoplay blocked:', error);
                    this.backgroundMusic.muted = false;
                    this.backgroundMusic.volume = this.isMuted ? 0 : this.audioVolume;
                    this.showPlayMusicNotification(musicPath);
                });
        }
    }

    showPlayMusicNotification(musicPath) {
        console.log('AudioManager: Showing play music notification for', musicPath);
        
        fetch(musicPath)
            .then(response => {
                console.log('AudioManager: Fetch response for', musicPath, 'Status:', response.status, 'OK:', response.ok);
                console.log('AudioManager: Response headers:', Object.fromEntries(response.headers.entries()));
                if (!response.ok) {
                    console.warn('AudioManager: Fetch failed with status', response.status);
                    return false;
                }
                return true;
            })
            .then(musicExists => {
                console.log('AudioManager: Music exists check result:', musicExists);
                const existingNotification = document.getElementById('playMusicNotification');
                if (existingNotification) {
                    existingNotification.remove();
                }
                
                console.log('AudioManager: Creating notification');
                const notificationHTML = `
                    <div id="playMusicNotification" class="position-fixed top-0 start-50 translate-middle-x p-3 mt-2" 
                        style="z-index: 1050; max-width: 300px;">
                        <div class="toast show bg-dark text-light" role="alert">
                            <div class="toast-header bg-dark text-light border-bottom border-secondary">
                                <i class="bi bi-music-note me-2"></i>
                                <strong class="me-auto">Música de Fundo</strong>
                                <button type="button" class="btn-close btn-close-white" 
                                    onclick="document.getElementById('playMusicNotification').remove()"></button>
                            </div>
                            <div class="toast-body">
                                <p class="small mb-2">Iniciar música temática?</p>
                                <button id="startMusicBtn" class="btn btn-sm btn-outline-light w-100">
                                    <i class="bi bi-play-fill"></i> Tocar Música
                                </button>
                            </div>
                        </div>
                    </div>
                `;
                
                document.body.insertAdjacentHTML('beforeend', notificationHTML);
                console.log('AudioManager: Notification inserted');
                
                document.getElementById('startMusicBtn').addEventListener('click', () => {
                    console.log('AudioManager: Play button clicked');
                    this.backgroundMusic.play()
                        .then(() => {
                            console.log('AudioManager: Music playback started');
                            document.getElementById('playMusicNotification').remove();
                        })
                        .catch(error => {
                            console.error('AudioManager: Failed to play music:', error);
                            const notificationBody = document.querySelector('#playMusicNotification .toast-body');
                            if (notificationBody) {
                                notificationBody.innerHTML = `
                                    <p class="small text-warning mb-2">Não foi possível iniciar a música. Verifique as configurações do seu navegador.</p>
                                    <button class="btn btn-sm btn-outline-light w-100" 
                                        onclick="document.getElementById('playMusicNotification').remove()">
                                        Fechar
                                    </button>
                                `;
                            }
                        });
                });
            })
            .catch(error => {
                console.error('AudioManager: Error checking music file:', error);
                this.showNotificationFallback(musicPath);
            });
    }

    showNotificationFallback(musicPath) {
        console.log('AudioManager: Showing fallback notification for', musicPath);
        const existingNotification = document.getElementById('playMusicNotification');
        if (existingNotification) {
            existingNotification.remove();
        }
        
        const notificationHTML = `
            <div id="playMusicNotification" class="position-fixed top-0 start-50 translate-middle-x p-3 mt-2" 
                style="z-index: 1050; max-width: 300px;">
                <div class="toast show bg-dark text-light" role="alert">
                    <div class="toast-header bg-dark text-light border-bottom border-secondary">
                        <i class="bi bi-music-note me-2"></i>
                        <strong class="me-auto">Música de Fundo</strong>
                        <button type="button" class="btn-close btn-close-white" 
                            onclick="document.getElementById('playMusicNotification').remove()"></button>
                    </div>
                    <div class="toast-body">
                        <p class="small mb-2">Iniciar música temática? (Verificação falhou)</p>
                        <button id="startMusicBtn" class="btn btn-sm btn-outline-light w-100">
                            <i class="bi bi-play-fill"></i> Tocar Música
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', notificationHTML);
        console.log('AudioManager: Fallback notification inserted');
        
        document.getElementById('startMusicBtn').addEventListener('click', () => {
            console.log('AudioManager: Fallback play button clicked');
            this.backgroundMusic.play()
                .then(() => {
                    console.log('AudioManager: Music playback started (fallback)');
                    document.getElementById('playMusicNotification').remove();
                })
                .catch(error => {
                    console.error('AudioManager: Failed to play music (fallback):', error);
                    const notificationBody = document.querySelector('#playMusicNotification .toast-body');
                    if (notificationBody) {
                        notificationBody.innerHTML = `
                            <p class="small text-warning mb-2">Não foi possível iniciar a música. Verifique as configurações do seu navegador.</p>
                            <button class="btn btn-sm btn-outline-light w-100" 
                                onclick="document.getElementById('playMusicNotification').remove()">
                                Fechar
                            </button>
                        `;
                    }
                });
        });
    }
}