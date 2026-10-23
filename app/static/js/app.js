/**
 * Kua Alpine.js Application — Celeste Marino (#0083B0) Theme
 * Quokka Mascot, Auth, Instagram-Style Forum, Study Customization, Deck Cloning, SM-2 Flashcards & Oral Exam
 */

document.addEventListener('alpine:init', () => {
    Alpine.data('vivaVoceApp', () => ({
        // Navigation: 'home', 'library', 'study', 'quiz', 'oral', 'forum', 'dashboard'
        currentTab: 'home',
        profileAvatarUrl: null,
        bannerColor: '#0083B0',

        // System status & API Key
        hasApiKey: false,
        maskedKey: '',
        apiKeyModalOpen: false,
        apiKeyInput: '',
        statusMessage: '',

        // Authentication & Current User
        currentUser: {
            id: 1,
            display_name: 'Estudiante Kua',
            username: 'estudiante_kua',
            email: 'demo@kua.edu',
            university: 'Universidad Nacional',
            career: 'Ingeniería de Sistemas',
            semester: '7mo Semestre',
            fruits_count: 6,
            quokka_happiness: 85,
            bio: 'Amante del estudio activo, la oratoria y los quokkas.'
        },
        authModalOpen: false,
        isAuthenticated: false,
        authMode: 'login', // 'login' or 'register'
        loginIdentifier: 'estudiante_kua',
        loginPassword: '',
        regDisplayName: '',
        regUsername: '',
        regEmail: '',
        regPassword: '',
        regUniversity: '',
        regCareer: '',
        regSemester: '',
        authError: '',

        // My Profile (edit view)
        profileEditName: '',
        profileEditEmail: '',
        profileEditUniversity: '',
        profileEditCareer: '',
        profileEditSemester: '',
        profileEditBio: '',
        profileSaving: false,

        // Public Profile Modal
        userProfileModalOpen: false,
        viewedUserProfile: null,

        // Quokka Mascot & Gamification
        quokkaStatus: {
            fruits_count: 6,
            quokka_happiness: 85,
            mood: '¡Muy alegre y listo para estudiar! 🌿'
        },
        quokkaEating: false,
        quokkaFeedSuccess: '',

        // Decks
        decks: [],
        folders: [],
        selectedFolder: null,
        newDeckFolderId: '',
        folderModalOpen: false,
        folderNameInput: '',
        isCreatingFolder: false,
        folderEditingId: null,
        folderColorInput: '#0083B0',
        folderImageFile: null,
        folderImageName: '',
        isGeneratingFolderOralExam: false,
        oralExamConfigOpen: false,
        oralExamTargetDeck: null,
        oralExamTargetFolder: null,
        oralQuestionCount: 6,
        oralDifficulty: 'Medio',
        selectedDeck: null,
        searchQuery: '',
        isLoadingDecks: false,

        // Upload / Generation with Study Customization
        uploadModalOpen: false,
        uploadMode: 'file', // 'file' or 'text'
        uploadFileName: '',
        uploadText: '',
        uploadDeckName: '',
        customSubject: 'General',
        customDifficulty: 'Medio', // 'Fácil', 'Medio', 'Difícil'
        customFlashcardsCount: 8,  // 5 to 30
        customQuizCount: 4,        // 3 to 15
        customOralCount: 3,        // 2 to 8
        customIsPublic: false,     // Share directly in forum
        isGeneratingDeck: false,
        generationMessage: '',

        // Study (Flashcards SM-2)
        studyDeck: null,
        flashcards: [],
        currentCardIndex: 0,
        isFlipped: false,
        studyCompleted: false,
        studyStats: { total: 0, reviewed: 0, easy: 0, hard: 0 },

        // Quiz
        quizDeck: null,
        quizQuestions: [],
        currentQuizIndex: 0,
        selectedOptionIndex: null,
        isOptionSubmitted: false,
        quizScore: 0,
        quizStreak: 0,
        quizCompleted: false,

        // Oral Exam with Auto-Countdown Flow
        oralDeck: null,
        oralQuestions: [],
        currentOralIndex: 0,
        oralSessionId: null,
        isCountingDown: false,
        countdownNumber: 3,
        countdownText: '3',
        isRecording: false,
        recordingTime: '00:00',
        isEvaluating: false,
        evalStepMessage: '',
        evaluationResult: null,
        oralSessionCompleted: false,
        oralSessionSummary: null,
        isPlayingTTS: false,

        // Instagram-style Community Forum
        forumPosts: [],
        forumModalOpen: false,
        forumUploadMode: 'text',
        forumTitle: '',
        forumSubject: 'General',
        forumDifficulty: 'Medio',
        forumDescription: '',
        forumText: '',
        forumFileName: '',
        isSubmittingForumPost: false,
        forumPostMessage: '',
        newComments: {}, // { [postId]: text }

        // Dashboard
        dashboardStats: null,
        selectedAnswerDetail: null,

        async init() {
            const authenticated = await this.restoreSession();
            if (authenticated) {
                this.syncProfileAppearance();
                await this.checkSystemStatus();
                await this.loadQuokkaStatus();
                await this.loadDecks();
                await this.loadFolders();
            }
            this.setupKeyboardShortcuts();
            this.$nextTick(() => {
                if (window.lucide) lucide.createIcons();
            });
        },

        // ==================== AUTHENTICATION ====================

        initLocalUser() {
            const saved = localStorage.getItem('kua_user');
            if (saved) {
                try {
                    this.currentUser = JSON.parse(saved);
                } catch (e) {
                    console.error("Error parsing stored user:", e);
                }
            }
        },

        syncProfileAppearance() {
            this.profileAvatarUrl = this.currentUser.profile_image || null;
            this.bannerColor = this.currentUser.banner_color || '#0083B0';
            this.$nextTick(() => {
                const banner = document.getElementById('profileBanner');
                const picker = document.getElementById('bannerColorPicker');
                if (banner) banner.style.backgroundColor = this.bannerColor;
                if (picker) picker.value = this.bannerColor;
            });
        },

        async restoreSession() {
            const token = localStorage.getItem('kua_session');
            if (!token) {
                localStorage.removeItem('kua_user');
                this.isAuthenticated = false;
                this.authModalOpen = true;
                return false;
            }
            try {
                const res = await fetch('/api/auth/session', {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (!res.ok) throw new Error('Sesión inválida');
                const data = await res.json();
                this.currentUser = data.user;
                localStorage.setItem('kua_user', JSON.stringify(this.currentUser));
                this.isAuthenticated = true;
                this.authModalOpen = false;
                return true;
            } catch (e) {
                localStorage.removeItem('kua_session');
                localStorage.removeItem('kua_user');
                localStorage.removeItem('token');
                this.isAuthenticated = false;
                this.authModalOpen = true;
                return false;
            }
        },

        async loadCurrentUser() {
            try {
                const res = await fetch(`/api/auth/me?user_id=${this.currentUser.id || 1}`);
                if (res.ok) {
                    this.currentUser = await res.json();
                    localStorage.setItem('kua_user', JSON.stringify(this.currentUser));
                }
            } catch (e) {
                console.error("Error loading current user:", e);
            }
        },

        async login() {
            this.authError = '';
            if (!this.loginIdentifier || !this.loginPassword) {
                this.authError = 'Por favor ingresa usuario/correo y contraseña.';
                return;
            }
            try {
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        username_or_email: this.loginIdentifier.trim(),
                        password: this.loginPassword
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    this.currentUser = data.user;
                    this.syncProfileAppearance();
                    localStorage.setItem('kua_session', data.session_token);
                    localStorage.setItem('kua_user', JSON.stringify(this.currentUser));
                    this.isAuthenticated = true;
                    this.authModalOpen = false;
                    this.loginPassword = '';
                    await this.checkSystemStatus();
                    await this.loadQuokkaStatus();
                    await this.loadDecks();
                    await this.loadFolders();
                    this.showToast(`¡Bienvenido de nuevo, @${this.currentUser.username}! 🌿`);
                    this.setTab('home');
                } else {
                    this.authError = data.detail || 'Error en el inicio de sesión.';
                }
            } catch (e) {
                this.authError = 'Error de conexión: ' + e.message;
            }
        },

        async register() {
            this.authError = '';
            if (!this.regDisplayName || !this.regUsername || !this.regEmail || !this.regPassword) {
                this.authError = 'Nombre, usuario (@handle), correo y contraseña son obligatorios.';
                return;
            }
            try {
                const res = await fetch('/api/auth/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        display_name: this.regDisplayName.trim(),
                        username: this.regUsername.trim(),
                        email: this.regEmail.trim(),
                        password: this.regPassword,
                        university: this.regUniversity.trim() || null,
                        career: this.regCareer.trim() || null,
                        semester: this.regSemester.trim() || null
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    this.currentUser = data.user;
                    this.syncProfileAppearance();
                    localStorage.setItem('kua_session', data.session_token);
                    localStorage.setItem('kua_user', JSON.stringify(this.currentUser));
                    this.isAuthenticated = true;
                    this.authModalOpen = false;
                    this.regPassword = '';
                    await this.checkSystemStatus();
                    await this.loadQuokkaStatus();
                    await this.loadDecks();
                    await this.loadFolders();
                    this.showToast(`🎉 ¡Cuenta creada con éxito! Bienvenido a Kua, @${this.currentUser.username}`);
                    this.setTab('home');
                } else {
                    this.authError = data.detail || 'Error en el registro.';
                }
            } catch (e) {
                this.authError = 'Error de conexión: ' + e.message;
            }
        },

        async switchDemoUser(userId) {
            try {
                const res = await fetch(`/api/auth/demo/${userId}`, { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    this.currentUser = data.user;
                    this.syncProfileAppearance();
                    localStorage.setItem('kua_session', data.session_token);
                    localStorage.setItem('kua_user', JSON.stringify(this.currentUser));
                    this.isAuthenticated = true;
                    this.authModalOpen = false;
                    await this.checkSystemStatus();
                    await this.loadQuokkaStatus();
                    await this.loadDecks();
                    await this.loadFolders();
                    this.showToast(`Cambiado a usuario demo: @${this.currentUser.username}`);
                }
            } catch (e) {
                console.error("Error switching user:", e);
            }
        },

        async logout() {
            const token = localStorage.getItem('kua_session');
            try {
                await fetch('/api/auth/logout', {
                    method: 'POST',
                    headers: token ? { 'Authorization': `Bearer ${token}` } : {}
                });
            } catch (e) {
                console.error('Error cerrando sesión en el servidor:', e);
            }
            localStorage.removeItem('kua_session');
            localStorage.removeItem('kua_user');
            localStorage.removeItem('token');
            window.location.replace('/');
        },

        async updateProfile() {
            if (!this.profileEditName.trim()) {
                this.showToast('⚠️ El nombre no puede estar vacío.');
                return;
            }
            this.profileSaving = true;
            try {
                const res = await fetch(`/api/user/profile?user_id=${this.currentUser.id || 1}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        display_name: this.profileEditName.trim(),
                        email:        this.profileEditEmail.trim() || null,
                        bio:          this.profileEditBio.trim() || null,
                        university:   this.profileEditUniversity.trim() || null,
                        career:       this.profileEditCareer.trim() || null,
                        semester:     this.profileEditSemester.trim() || null,
                        banner_color: this.bannerColor
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    // Update local user
                    this.currentUser.display_name = this.profileEditName.trim();
                    this.currentUser.email        = this.profileEditEmail.trim();
                    this.currentUser.university   = this.profileEditUniversity.trim();
                    this.currentUser.career       = this.profileEditCareer.trim();
                    this.currentUser.semester     = this.profileEditSemester.trim();
                    this.currentUser.bio          = this.profileEditBio.trim();
                    this.currentUser.banner_color = this.bannerColor;
                    if (data.user) Object.assign(this.currentUser, data.user);
                    localStorage.setItem('kua_user', JSON.stringify(this.currentUser));
                    this.syncProfileAppearance();
                    this.showToast('✅ Perfil actualizado con éxito.');
                } else {
                    this.showToast('⚠️ ' + (data.detail || 'Error al guardar cambios.'));
                }
            } catch (e) {
                this.showToast('❌ Error de conexión: ' + e.message);
            } finally {
                this.profileSaving = false;
            }
        },

        async viewUserProfile(userId) {
            try {
                const res = await fetch(`/api/users/${userId}/public`);
                if (res.ok) {
                    this.viewedUserProfile = await res.json();
                    this.userProfileModalOpen = true;
                    this.$nextTick(() => {
                        if (window.lucide) lucide.createIcons();
                    });
                } else {
                    alert("No se pudo cargar el perfil del usuario.");
                }
            } catch (e) {
                alert("Error al cargar perfil: " + e.message);
            }
        },

        // ==================== QUOKKA MASCOT & GAMIFICATION ====================

        async loadQuokkaStatus() {
            try {
                const res = await fetch(`/api/quokka/status?user_id=${this.currentUser.id || 1}`);
                if (res.ok) {
                    this.quokkaStatus = await res.json();
                    this.currentUser.fruits_count = this.quokkaStatus.fruits_count;
                    this.currentUser.quokka_happiness = this.quokkaStatus.quokka_happiness;
                }
            } catch (e) {
                console.error("Error loading Quokka status:", e);
            }
        },

        async feedQuokka() {
            if ((this.quokkaStatus.fruits_count || 0) <= 0) {
                alert("¡No tienes frutas suficientes! Completa una sesión de flashcards, quiz o examen oral para recolectar frutas.");
                return;
            }
            try {
                const res = await fetch(`/api/quokka/feed?user_id=${this.currentUser.id || 1}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ fruit_type: 'fresa' })
                });
                const data = await res.json();
                if (res.ok) {
                    this.quokkaEating = true;
                    this.quokkaStatus.fruits_count = data.fruits_count;
                    this.quokkaStatus.quokka_happiness = data.quokka_happiness;
                    this.currentUser.fruits_count = data.fruits_count;
                    this.currentUser.quokka_happiness = data.quokka_happiness;
                    this.quokkaFeedSuccess = data.message;
                    this.showToast("🍓 ¡Koko está comiendo feliz!");

                    setTimeout(() => {
                        this.quokkaEating = false;
                    }, 2600);
                } else {
                    alert(data.detail || 'Error alimentando al Quokka');
                }
            } catch (e) {
                alert("Error de conexión: " + e.message);
            }
        },

        async awardFruit(sessionType) {
            try {
                const res = await fetch(`/api/quokka/award-fruit?user_id=${this.currentUser.id || 1}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_type: sessionType })
                });
                if (res.ok) {
                    const data = await res.json();
                    this.quokkaStatus.fruits_count = data.fruits_count;
                    this.quokkaStatus.quokka_happiness = data.quokka_happiness;
                    this.currentUser.fruits_count = data.fruits_count;
                    this.currentUser.quokka_happiness = data.quokka_happiness;
                    this.showToast(data.message);
                }
            } catch (e) {
                console.error("Error awarding fruit:", e);
            }
        },

        // ==================== SYSTEM & KEY ====================

        async checkSystemStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                this.hasApiKey = data.has_gemini_api_key;
                this.maskedKey = data.masked_key || '';
            } catch (e) {
                console.error("Status check failed:", e);
            }
        },

        async saveApiKey() {
            if (!this.apiKeyInput.trim()) return;
            try {
                const res = await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ gemini_api_key: this.apiKeyInput.trim() })
                });
                if (res.ok) {
                    this.hasApiKey = true;
                    this.apiKeyModalOpen = false;
                    this.apiKeyInput = '';
                    await this.checkSystemStatus();
                    this.showToast('✅ Clave de Gemini API guardada con éxito.');
                } else {
                    const err = await res.json();
                    alert(err.detail || 'Error al guardar clave');
                }
            } catch (e) {
                alert('Error al conectar con el servidor: ' + e.message);
            }
        },

        showToast(msg) {
            this.statusMessage = msg;
            setTimeout(() => {
                this.statusMessage = '';
            }, 3800);
        },

        setTab(tab) {
            this.currentTab = tab;
            document.querySelector('main')?.scrollTo({ top: 0, behavior: 'smooth' });

            this.$nextTick(() => {
                if (window.lucide) lucide.createIcons();
                if (tab === 'dashboard') {
                    this.loadDashboardStats();
                    this.loadQuokkaStatus();
                } else if (tab === 'forum') {
                    this.loadForumPosts();
                } else if (tab === 'library') {
                    this.loadDecks();
                    this.loadFolders();
                } else if (tab === 'profile') {
                    this.syncProfileAppearance();
                    // Pre-fill profile fields with current user data
                    this.profileEditName       = this.currentUser.display_name || '';
                    this.profileEditEmail      = this.currentUser.email || '';
                    this.profileEditUniversity = this.currentUser.university || '';
                    this.profileEditCareer     = this.currentUser.career || '';
                    this.profileEditSemester   = this.currentUser.semester || '';
                    this.profileEditBio        = this.currentUser.bio || '';
                }
            });
        },

        // ==================== DECKS & PRIVACY ====================

        async loadDecks() {
            this.isLoadingDecks = true;
            try {
                const res = await fetch(`/api/decks?user_id=${this.currentUser.id || 1}`);
                this.decks = await res.json();
            } catch (e) {
                console.error("Error loading decks:", e);
            } finally {
                this.isLoadingDecks = false;
                this.$nextTick(() => {
                    if (window.lucide) lucide.createIcons();
                });
            }
        },

        async loadFolders() {
            try {
                const res = await fetch(`/api/folders?user_id=${this.currentUser.id || 1}`);
                if (!res.ok) throw new Error('No se pudieron cargar las carpetas.');
                this.folders = await res.json();
                if (this.selectedFolder) {
                    this.selectedFolder = this.folders.find(folder => folder.id === this.selectedFolder.id) || null;
                }
            } catch (e) {
                console.error('Error loading folders:', e);
                this.folders = [];
            }
        },

        openFolder(folder) {
            this.selectedFolder = folder;
            this.newDeckFolderId = String(folder.id);
            document.querySelector('main')?.scrollTo({ top: 0, behavior: 'smooth' });
        },

        openFolderEditor(folder = null) {
            this.folderEditingId = folder ? folder.id : null;
            this.folderNameInput = folder?.name || '';
            this.folderColorInput = folder?.color || '#0083B0';
            this.folderImageFile = null;
            this.folderImageName = folder?.image_path ? 'Foto actual (elige otra para reemplazarla)' : '';
            this.folderModalOpen = true;
        },

        async saveFolder() {
            const name = this.folderNameInput.trim();
            if (!name) return;
            this.isCreatingFolder = true;
            try {
                const formData = new FormData();
                formData.append('name', name);
                formData.append('color', this.folderColorInput);
                if (this.folderImageFile) formData.append('image', this.folderImageFile);
                const isEditing = Boolean(this.folderEditingId);
                const url = isEditing
                    ? `/api/folders/${this.folderEditingId}?user_id=${this.currentUser.id || 1}`
                    : `/api/folders?user_id=${this.currentUser.id || 1}`;
                const res = await fetch(url, { method: isEditing ? 'PATCH' : 'POST', body: formData });
                const data = await res.json();
                if (!res.ok) {
                    this.showToast('⚠️ ' + (data.detail || 'No se pudo crear la carpeta.'));
                    return;
                }
                await this.loadFolders();
                this.folderNameInput = '';
                this.folderImageFile = null;
                this.folderImageName = '';
                this.folderEditingId = null;
                this.folderModalOpen = false;
                this.showToast(isEditing ? `📁 Carpeta "${data.name}" actualizada.` : `📁 Carpeta "${data.name}" creada.`);
            } catch (e) {
                this.showToast('❌ Error creando carpeta: ' + e.message);
            } finally {
                this.isCreatingFolder = false;
            }
        },

        async createFolder() {
            this.folderEditingId = null;
            await this.saveFolder();
        },

        async updateFolder() {
            await this.saveFolder();
        },

        async moveDeckToFolder(deck, folderId) {
            const parsedFolderId = folderId ? Number(folderId) : null;
            try {
                const res = await fetch(`/api/decks/${deck.id}/folder?user_id=${this.currentUser.id || 1}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ folder_id: parsedFolderId })
                });
                const data = await res.json();
                if (!res.ok) {
                    this.showToast('⚠️ ' + (data.detail || 'No se pudo mover el mazo.'));
                    return;
                }
                deck.folder_id = parsedFolderId;
                await this.loadFolders();
                this.showToast('✅ Mazo movido correctamente.');
            } catch (e) {
                this.showToast('❌ Error moviendo el mazo: ' + e.message);
            }
        },

        async startFolderOralExam(folder) {
            this.oralExamTargetFolder = folder;
            this.oralExamTargetDeck = null;
            this.oralExamConfigOpen = true;
        },

        async confirmOralExam() {
            const folder = this.oralExamTargetFolder;
            const deck = this.oralExamTargetDeck;
            if (!folder && !deck) return;
            this.isGeneratingFolderOralExam = true;
            try {
                const url = folder
                    ? `/api/folders/${folder.id}/oral-exam?user_id=${this.currentUser.id || 1}`
                    : `/api/decks/${deck.id}/oral-exam?user_id=${this.currentUser.id || 1}`;
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        question_count: Number(this.oralQuestionCount),
                        difficulty: this.oralDifficulty
                    })
                });
                const data = await res.json();
                if (!res.ok) {
                    this.showToast('⚠️ ' + (data.detail || 'No se pudo generar el examen de la carpeta.'));
                    return;
                }
                this.oralExamConfigOpen = false;
                this.showToast(`🎙️ Examen listo: ${data.question_count} preguntas (${this.oralDifficulty}).`);
                await this.runOralExam(data.deck);
            } catch (e) {
                this.showToast('❌ Error generando el examen: ' + e.message);
            } finally {
                this.isGeneratingFolderOralExam = false;
            }
        },

        filteredDecks() {
            const decksInView = this.selectedFolder
                ? this.decks.filter(deck => deck.folder_id === this.selectedFolder.id)
                : this.decks.filter(deck => deck.folder_id == null);
            if (!this.searchQuery.trim()) return decksInView;
            const q = this.searchQuery.toLowerCase();
            return decksInView.filter(d => 
                (d.name && d.name.toLowerCase().includes(q)) || 
                (d.subject && d.subject.toLowerCase().includes(q)) ||
                (d.notes_text && d.notes_text.toLowerCase().includes(q))
            );
        },

        async toggleDeckPrivacy(deck, event) {
            if (event) event.stopPropagation();
            const newStatus = !deck.is_public;
            try {
                const res = await fetch(`/api/decks/${deck.id}/privacy?user_id=${this.currentUser.id || 1}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_public: newStatus })
                });
                const data = await res.json();
                if (res.ok) {
                    deck.is_public = newStatus;
                    this.showToast(data.message);
                } else {
                    alert(data.detail || "Error cambiando privacidad del mazo");
                }
            } catch (e) {
                alert("Error de conexión: " + e.message);
            }
        },

        async deleteDeck(deckId, event) {
            if (event) event.stopPropagation();
            if (!confirm("¿Estás seguro de que deseas eliminar este mazo? Se borrarán sus flashcards, quizzes y preguntas orales.")) {
                return;
            }
            try {
                const res = await fetch(`/api/decks/${deckId}`, { method: 'DELETE' });
                if (res.ok) {
                    await this.loadDecks();
                    this.showToast("Mazo eliminado correctamente.");
                }
            } catch (e) {
                alert("Error al eliminar mazo: " + e.message);
            }
        },

        // ==================== GENERATION / UPLOAD WITH CUSTOMIZATION ====================

        handleFileSelected(event) {
            const file = event.target.files[0];
            if (file) {
                this.uploadFileName = file.name;
                if (!this.uploadDeckName) {
                    this.uploadDeckName = file.name.replace(/\.[^/.]+$/, "");
                }
            }
        },

        handleForumFileSelected(event) {
            const file = event.target.files[0];
            if (file) {
                this.forumFileName = file.name;
                if (!this.forumTitle) {
                    this.forumTitle = file.name.replace(/\.[^/.]+$/, "");
                }
            }
        },

        async generateDeck() {
            if (!this.hasApiKey) {
                this.apiKeyModalOpen = true;
                return;
            }

            this.isGeneratingDeck = true;
                this.generationMessage = "Analizando apuntes de estudio...";

            try {
                let res;
                if (this.uploadMode === 'file') {
                    const fileInput = document.getElementById('deckFileInput');
                    if (!fileInput || !fileInput.files[0]) {
                        alert("Por favor selecciona un archivo PDF o TXT.");
                        this.isGeneratingDeck = false;
                        return;
                    }

                    const formData = new FormData();
                    formData.append('file', fileInput.files[0]);
                    formData.append('custom_name', this.uploadDeckName || '');
                    formData.append('subject', this.customSubject || 'General');
                    formData.append('difficulty', this.customDifficulty || 'Medio');
                    formData.append('flashcards_count', this.customFlashcardsCount);
                    formData.append('quiz_count', this.customQuizCount);
                    formData.append('oral_count', this.customOralCount);
                    formData.append('is_public', this.customIsPublic ? 'true' : 'false');
                    if (this.newDeckFolderId) formData.append('folder_id', this.newDeckFolderId);
                    formData.append('user_id', this.currentUser.id || 1);

                    this.generationMessage = 'Generando mazo...';
                    res = await fetch('/api/decks/generate-from-file', {
                        method: 'POST',
                        body: formData
                    });
                } else {
                    if (!this.uploadText || this.uploadText.trim().length < 30) {
                        alert("Por favor introduce suficiente texto de tus apuntes (mínimo 30 caracteres).");
                        this.isGeneratingDeck = false;
                        return;
                    }

                    this.generationMessage = 'Generando mazo...';
                    res = await fetch(`/api/decks/generate-from-text?user_id=${this.currentUser.id || 1}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: this.uploadDeckName || null,
                            notes_text: this.uploadText,
                            subject: this.customSubject || 'General',
                            difficulty: this.customDifficulty || 'Medio',
                            flashcards_count: parseInt(this.customFlashcardsCount),
                            quiz_count: parseInt(this.customQuizCount),
                            oral_count: parseInt(this.customOralCount),
                            is_public: Boolean(this.customIsPublic),
                            folder_id: this.newDeckFolderId ? Number(this.newDeckFolderId) : null
                        })
                    });
                }

                if (res.ok) {
                    const result = await res.json();
                    this.generationMessage = 'Generando mazo...';
                    const completed = await this.pollGenerationJob(result.job_id, 'deck');
                    this.uploadModalOpen = false;
                    this.uploadFileName = '';
                    this.uploadText = '';
                    this.uploadDeckName = '';
                    this.newDeckFolderId = '';
                    await this.loadDecks();
                    this.showToast(`✨ Mazo "${completed.name}" creado con éxito.`);
                    this.setTab('library');
                } else {
                    const err = await res.json();
                    alert("Aviso: " + (err.detail || 'Ocurrió un problema generando el mazo'));
                }
            } catch (e) {
                alert("Error de red: " + e.message);
            } finally {
                this.isGeneratingDeck = false;
                this.generationMessage = '';
            }
        },

        async pollGenerationJob(jobId, channel = 'deck') {
            while (true) {
                await new Promise(resolve => setTimeout(resolve, 2000));
                const res = await fetch(`/api/generation-jobs/${jobId}?user_id=${this.currentUser.id || 1}`);
                const job = await res.json();
                if (!res.ok) throw new Error(job.detail || 'No se pudo consultar el estado de generación.');
                const message = job.message || 'Generando mazo...';
                if (channel === 'forum') this.forumPostMessage = message;
                else this.generationMessage = message;
                if (job.status === 'completed') return job;
                if (job.status === 'failed') throw new Error(job.error || 'Falló la generación del mazo.');
            }
        },

        // ==================== STUDY (SM-2 FLASHCARDS) ====================

        async startStudy(deck) {
            this.studyDeck = deck;
            this.currentCardIndex = 0;
            this.isFlipped = false;
            this.studyCompleted = false;
            this.studyStats = { total: 0, reviewed: 0, easy: 0, hard: 0 };

            try {
                const res = await fetch(`/api/decks/${deck.id}/flashcards`);
                this.flashcards = await res.json();
                this.studyStats.total = this.flashcards.length;
                this.setTab('study');
            } catch (e) {
                alert("Error cargando flashcards: " + e.message);
            }
        },

        flipCard() {
            this.isFlipped = !this.isFlipped;
        },

        async rateCard(grade) {
            if (!this.flashcards.length) return;
            const currentCard = this.flashcards[this.currentCardIndex];
            
            this.studyStats.reviewed++;
            if (grade >= 4) this.studyStats.easy++;
            if (grade < 3) this.studyStats.hard++;

            try {
                await fetch(`/api/flashcards/${currentCard.id}/review`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ grade: grade })
                });
            } catch (e) {
                console.error("Error saving SM-2 review:", e);
            }

            this.isFlipped = false;
            if (this.currentCardIndex + 1 < this.flashcards.length) {
                this.currentCardIndex++;
            } else {
                this.studyCompleted = true;
                // Premia al usuario con frutas para su Quokka
                await this.awardFruit('flashcards');
            }
        },

        setupKeyboardShortcuts() {
            window.addEventListener('keydown', (e) => {
                if (this.currentTab === 'study' && !this.studyCompleted && this.flashcards.length > 0) {
                    if (e.code === 'Space') {
                        e.preventDefault();
                        this.flipCard();
                    } else if (this.isFlipped && ['Digit1', 'Digit2', 'Digit3', 'Digit4', 'Digit5'].includes(e.code)) {
                        const grade = parseInt(e.code.replace('Digit', ''));
                        this.rateCard(grade);
                    }
                }
            });
        },

        // ==================== QUIZ ====================

        async startQuiz(deck) {
            this.quizDeck = deck;
            this.currentQuizIndex = 0;
            this.selectedOptionIndex = null;
            this.isOptionSubmitted = false;
            this.quizScore = 0;
            this.quizStreak = 0;
            this.quizCompleted = false;

            try {
                const res = await fetch(`/api/decks/${deck.id}/quiz`);
                this.quizQuestions = await res.json();
                if (this.quizQuestions.length === 0) {
                    alert("Este mazo no tiene preguntas de quiz aún.");
                    return;
                }
                this.setTab('quiz');
            } catch (e) {
                alert("Error cargando quiz: " + e.message);
            }
        },

        selectQuizOption(idx) {
            if (this.isOptionSubmitted) return;
            this.selectedOptionIndex = idx;
            this.isOptionSubmitted = true;

            const q = this.quizQuestions[this.currentQuizIndex];
            if (idx === q.correct_index) {
                this.quizScore++;
                this.quizStreak++;
            } else {
                this.quizStreak = 0;
            }
        },

        nextQuizQuestion() {
            if (this.currentQuizIndex + 1 < this.quizQuestions.length) {
                this.currentQuizIndex++;
                this.selectedOptionIndex = null;
                this.isOptionSubmitted = false;
            } else {
                this.quizCompleted = true;
                this.saveQuizAttempt();
                // Premia al usuario con frutas
                this.awardFruit('quiz');
            }
        },

        async saveQuizAttempt() {
            if (!this.quizDeck) return;
            try {
                await fetch(`/api/quiz/attempt?user_id=${this.currentUser.id || 1}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        deck_id: this.quizDeck.id,
                        score: this.quizScore,
                        total_questions: this.quizQuestions.length
                    })
                });
            } catch (e) {
                console.error("Error saving quiz attempt:", e);
            }
        },

        // ==================== NUEVO FLUJO DE EXAMEN ORAL CON CONTEO (3, 2, 1) ====================

        startOralExam(deck) {
            this.oralExamTargetDeck = deck;
            this.oralExamTargetFolder = null;
            this.oralExamConfigOpen = true;
        },

        async runOralExam(deck) {
            this.oralDeck = deck;
            this.currentOralIndex = 0;
            this.evaluationResult = null;
            this.oralSessionCompleted = false;
            this.oralSessionSummary = null;
            this.isRecording = false;
            this.isEvaluating = false;
            this.isCountingDown = false;

            try {
                const res = await fetch(`/api/oral/sessions/start?user_id=${this.currentUser.id || 1}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ deck_id: deck.id })
                });
                const data = await res.json();
                this.oralSessionId = data.session_id;
                this.oralQuestions = data.questions;

                if (!this.oralQuestions || this.oralQuestions.length === 0) {
                    alert("Este mazo no tiene preguntas orales asignadas.");
                    return;
                }
                this.setTab('oral');

                // Iniciar automáticamente la cuenta regresiva visual y activar micrófono
                this.triggerOralCountdown();
            } catch (e) {
                alert("Error iniciando examen oral: " + e.message);
            }
        },

        triggerOralCountdown() {
            this.isCountingDown = true;
            this.countdownNumber = 3;
            this.countdownText = '3';
            this.evaluationResult = null;

            const interval = setInterval(() => {
                this.countdownNumber--;
                if (this.countdownNumber === 2) {
                    this.countdownText = '2';
                } else if (this.countdownNumber === 1) {
                    this.countdownText = '1';
                } else if (this.countdownNumber === 0) {
                    this.countdownText = '¡Habla ahora!';
                } else {
                    clearInterval(interval);
                    this.isCountingDown = false;
                    // ACTIVACIÓN AUTOMÁTICA DEL MICRÓFONO
                    this.startOralRecording();
                }
            }, 850);
        },

        async speakQuestionTTS() {
            if (!this.oralQuestions.length) return;
            const q = this.oralQuestions[this.currentOralIndex];
            this.isPlayingTTS = true;

            try {
                const res = await fetch('/api/oral/tts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: q.question_text })
                });

                if (res.status === 200) {
                    const blob = await res.blob();
                    const audioUrl = URL.createObjectURL(blob);
                    const audio = new Audio(audioUrl);
                    audio.onended = () => { this.isPlayingTTS = false; };
                    audio.onerror = () => { this.fallbackBrowserTTS(q.question_text); };
                    audio.play();
                    return;
                }
            } catch (e) {
                console.log("TTS fallback:", e);
            }

            this.fallbackBrowserTTS(q.question_text);
        },

        fallbackBrowserTTS(text) {
            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = 'es-ES';
                utterance.rate = 0.95;
                utterance.onend = () => { this.isPlayingTTS = false; };
                utterance.onerror = () => { this.isPlayingTTS = false; };
                window.speechSynthesis.speak(utterance);
            } else {
                this.isPlayingTTS = false;
            }
        },

        async startOralRecording() {
            try {
                const canvas = document.getElementById('oralWaveformCanvas');
                await window.vivaVoceAudio.startRecording(canvas, (timeStr) => {
                    this.recordingTime = timeStr;
                });
                this.isRecording = true;
                this.evaluationResult = null;
            } catch (err) {
                alert("No se pudo acceder al micrófono. Por favor concede permisos de audio en tu navegador.");
                this.isRecording = false;
            }
        },

        async stopOralRecordingAndEvaluate() {
            if (!this.isRecording) return;
            
            try {
                const { blob, mimeType } = await window.vivaVoceAudio.stopRecording();
                this.isRecording = false;
                this.isEvaluating = true;
                this.evalStepMessage = "1/2 Transcribiendo con gemini-3.5-transcribe...";

                const q = this.oralQuestions[this.currentOralIndex];
                const formData = new FormData();
                formData.append('audio', blob, 'respuesta_oral.webm');

                setTimeout(() => {
                    if (this.isEvaluating) {
                        this.evalStepMessage = "2/2 Evaluando contenido y fluidez con gemini-3.8-flash...";
                    }
                }, 1100);

                const res = await fetch(`/api/oral/sessions/${this.oralSessionId}/answer/${q.id}`, {
                    method: 'POST',
                    body: formData
                });

                if (res.ok) {
                    this.evaluationResult = await res.json();
                } else {
                    const err = await res.json();
                    alert("Aviso de evaluación: " + (err.detail || 'Error procesando respuesta'));
                }
            } catch (err) {
                alert("Error procesando audio: " + err.message);
            } finally {
                this.isEvaluating = false;
                this.evalStepMessage = '';
                this.$nextTick(() => {
                    if (window.lucide) lucide.createIcons();
                });
            }
        },

        cancelOralRecording() {
            window.vivaVoceAudio.cancelRecording();
            this.isRecording = false;
            this.recordingTime = '00:00';
        },

        nextOralQuestion() {
            this.evaluationResult = null;
            if (this.currentOralIndex + 1 < this.oralQuestions.length) {
                this.currentOralIndex++;
                this.triggerOralCountdown();
            } else {
                this.completeOralSession();
            }
        },

        async completeOralSession() {
            try {
                const res = await fetch(`/api/oral/sessions/${this.oralSessionId}/complete`, {
                    method: 'POST'
                });
                if (res.ok) {
                    this.oralSessionSummary = await res.json();
                    this.oralSessionCompleted = true;
                    // Examen oral da 2 frutas al Quokka
                    await this.awardFruit('oral');
                }
            } catch (e) {
                console.error("Error completing oral session:", e);
                this.oralSessionCompleted = true;
            }
        },

        // ==================== INSTAGRAM-STYLE FORUM FEED ====================

        async loadForumPosts() {
            try {
                const res = await fetch(`/api/forum/feed?current_user_id=${this.currentUser.id || 1}`);
                this.forumPosts = await res.json();
                this.$nextTick(() => {
                    if (window.lucide) lucide.createIcons();
                });
            } catch (e) {
                console.error("Error loading forum feed:", e);
            }
        },

        async toggleLikePost(post) {
            try {
                const res = await fetch(`/api/forum/posts/${post.id}/like?user_id=${this.currentUser.id || 1}`, { 
                    method: 'POST' 
                });
                if (res.ok) {
                    const data = await res.json();
                    post.likes_count = data.likes_count;
                    post.user_has_liked = data.liked;
                }
            } catch (e) {
                console.error("Error liking post:", e);
            }
        },

        async submitComment(post) {
            const text = (this.newComments[post.id] || '').trim();
            if (!text) return;

            try {
                const res = await fetch(`/api/forum/posts/${post.id}/comments?user_id=${this.currentUser.id || 1}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ comment_text: text })
                });
                if (res.ok) {
                    const data = await res.json();
                    if (!post.comments) post.comments = [];
                    post.comments.push(data.comment);
                    post.comments_count = (post.comments_count || 0) + 1;
                    this.newComments[post.id] = '';
                } else {
                    const err = await res.json();
                    alert(err.detail || "Error publicando comentario");
                }
            } catch (e) {
                alert("Error de conexión: " + e.message);
            }
        },

        async cloneForumDeck(post) {
            if (!post.deck_id) {
                alert("Esta publicación no tiene un mazo para clonar.");
                return;
            }
            try {
                const res = await fetch(`/api/decks/${post.deck_id}/clone?user_id=${this.currentUser.id || 1}`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (res.ok) {
                    await this.loadDecks();
                    this.showToast(`📥 ¡Mazo "${data.name}" guardado como copia en tu Biblioteca!`);
                } else {
                    alert(data.detail || "Error al guardar mazo en tu biblioteca");
                }
            } catch (e) {
                alert("Error de conexión: " + e.message);
            }
        },

        async submitForumPost() {
            if (!this.forumTitle.trim()) {
                alert("Por favor introduce un título para la publicación.");
                return;
            }

            this.isSubmittingForumPost = true;
            this.forumPostMessage = "1/3 Analizando apuntes con IA...";

            try {
                let res;
                if (this.forumUploadMode === 'file') {
                    const fileInput = document.getElementById('forumFileInput');
                    if (!fileInput || !fileInput.files[0]) {
                        alert("Por favor selecciona un archivo PDF o TXT.");
                        this.isSubmittingForumPost = false;
                        return;
                    }
                    const formData = new FormData();
                    formData.append('file', fileInput.files[0]);
                    formData.append('custom_name', this.forumTitle);
                    formData.append('subject', this.forumSubject || 'General');
                    formData.append('difficulty', this.forumDifficulty || 'Medio');
                    formData.append('is_public', 'true');
                    formData.append('user_id', this.currentUser.id || 1);

                    this.forumPostMessage = "Generando mazo...";
                    res = await fetch('/api/decks/generate-from-file', {
                        method: 'POST',
                        body: formData
                    });
                } else {
                    if (!this.forumText || this.forumText.trim().length < 30) {
                        alert("Por favor añade suficiente contenido de apuntes (mínimo 30 caracteres).");
                        this.isSubmittingForumPost = false;
                        return;
                    }
                    this.forumPostMessage = "Generando mazo...";
                    res = await fetch(`/api/decks/generate-from-text?user_id=${this.currentUser.id || 1}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: this.forumTitle,
                            notes_text: this.forumText,
                            subject: this.forumSubject || 'General',
                            difficulty: this.forumDifficulty || 'Medio',
                            is_public: true
                        })
                    });
                }

                if (res.ok) {
                    const result = await res.json();
                    this.forumPostMessage = 'Generando mazo...';
                    await this.pollGenerationJob(result.job_id, 'forum');
                    this.forumModalOpen = false;
                    this.forumTitle = '';
                    this.forumDescription = '';
                    this.forumText = '';
                    this.forumFileName = '';
                    await this.loadForumPosts();
                    await this.loadDecks();
                    this.showToast("🎉 ¡Apuntes publicados en el Foro con éxito!");
                } else {
                    const err = await res.json();
                    alert("Aviso: " + (err.detail || 'Error publicando en el foro'));
                }
            } catch (e) {
                alert("Error de red: " + e.message);
            } finally {
                this.isSubmittingForumPost = false;
                this.forumPostMessage = '';
            }
        },

        // ==================== DASHBOARD ====================

        async loadDashboardStats() {
            try {
                const res = await fetch(`/api/dashboard/stats?user_id=${this.currentUser.id || 1}`);
                this.dashboardStats = await res.json();

                setTimeout(() => {
                    if (window.vivaVoceCharts && this.dashboardStats) {
                        window.vivaVoceCharts.renderPerformanceChart('oralPerformanceChart', this.dashboardStats.timeline || []);
                        window.vivaVoceCharts.renderSkillsRadarChart('skillsRadarChart', this.dashboardStats);
                        window.vivaVoceCharts.renderSm2DistributionChart('sm2DistributionChart', this.dashboardStats);
                    }
                    if (window.lucide) lucide.createIcons();
                }, 100);
            } catch (e) {
                console.error("Error loading dashboard stats:", e);
            }
        },

        openAnswerDetail(ans) {
            this.selectedAnswerDetail = ans;
            this.$nextTick(() => {
                if (window.lucide) lucide.createIcons();
            });
        }
    }));
});
// 2. Cambiar el color del banner dinámicamente
function updateBannerColor(hexColor) {
    const banner = document.getElementById('profileBanner');
    if (banner) {
        banner.style.backgroundColor = hexColor;
    }
    const root = document.querySelector('[x-data]');
    const alpineData = root && Alpine.$data(root);
    if (alpineData) {
        alpineData.bannerColor = hexColor;
    }
}
// 1. Inicializa la propiedad en Alpine.js (en tu app.js)
// profileAvatarUrl: null,

// 2. Función para leer la imagen y guardarla en el estado de Alpine
function previewProfileAvatar(event) {
    const file = event.target.files[0];
    if (!file) return;
    const root = document.querySelector('[x-data]');
    const alpineData = root && Alpine.$data(root);
    if (!alpineData) return;

    const previousUrl = alpineData.profileAvatarUrl;
    const previewUrl = URL.createObjectURL(file);
    alpineData.profileAvatarUrl = previewUrl;

    const formData = new FormData();
    formData.append('file', file);
    const token = localStorage.getItem('kua_session');
    fetch(`/api/users/${alpineData.currentUser.id}/avatar`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        body: formData
    }).then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'No se pudo guardar la foto.');
        URL.revokeObjectURL(previewUrl);
        alpineData.profileAvatarUrl = data.profile_image;
        alpineData.currentUser.profile_image = data.profile_image;
        localStorage.setItem('kua_user', JSON.stringify(alpineData.currentUser));
        alpineData.showToast('✅ Foto de perfil guardada.');
    }).catch((error) => {
        URL.revokeObjectURL(previewUrl);
        alpineData.profileAvatarUrl = previousUrl;
        alpineData.showToast('⚠️ ' + error.message);
    });
}
