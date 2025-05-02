class AudioManager {
    constructor() {
        this.backgroundMusic = null;
        this.currentAmbientSound = null;
        this.audioVolume = 0.3; // Volume padrão (30%)
        this.isMuted = false;
        
        console.log('AudioManager: Initializing');
        this.initAudio();
    }
    
    initAudio() {
        if (!this.backgroundMusic) {
            this.backgroundMusic = new Audio();
            this.backgroundMusic.loop = true;
            this.backgroundMusic.volume = this.audioVolume;
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
                        <i class="bi bi-volume-up"></i>
                    </button>
                    <button id="musicVolumeBtn" class="btn btn-sm btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown">
                        Volume
                    </button>
                    <div class="dropdown-menu p-2 dropdown-menu-end">
                        <input type="range" id="volumeSlider" class="form-range" min="0" max="100" value="30">
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
        if (this.currentAmbientSound === ambientSound) {
            console.log('AudioManager: Ambient sound unchanged, skipping');
            return;
        }
        
        this.currentAmbientSound = ambientSound;
        
        console.log('AudioManager: Setting audio source to', musicPath);
        this.backgroundMusic.src = musicPath;
        
        this.showPlayMusicNotification(musicPath);
    }
    
    showPlayMusicNotification(musicPath) {
        console.log('AudioManager: Showing play music notification for', musicPath);
        
        fetch(musicPath, { method: 'HEAD' })
            .then(response => {
                console.log('AudioManager: Fetch response for', musicPath, 'Status:', response.status, 'OK:', response.ok);
                if (!response.ok) {
                    console.warn('AudioManager: Fetch failed with status', response.status);
                    throw new Error(`HTTP error! status: ${response.status}`);
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
                                    <p class="small text-warning mb-2">Não foi possível iniciar a música: ${error.message}. Verifique as configurações do seu navegador.</p>
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
                            <p class="small text-warning mb-2">Não foi possível iniciar a música: ${error.message}. Verifique as configurações do seu navegador.</p>
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

document.addEventListener('DOMContentLoaded', () => {
    console.log('AudioManager: DOMContentLoaded, initializing AudioManager');
    window.audioManager = new AudioManager();
    
    if (window.gameState && window.gameState.ambientSound && window.gameState.ambientSoundUrl) {
        console.log('AudioManager: Found gameState.ambientSound, playing:', window.gameState.ambientSound, 'at', window.gameState.ambientSoundUrl);
        window.audioManager.playAmbientSound(window.gameState.ambientSound, window.gameState.ambientSoundUrl);
    } else {
        console.warn('AudioManager: No gameState.ambientSound or ambientSoundUrl found');
    }
});