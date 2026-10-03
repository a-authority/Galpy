/*!
 * GalPy Web 播放器运行时 —— 忠实复刻 galpy/engine/player.py 的 GamePlayer。
 *
 * 与 Qt 端共享同一份 project.json 数据源, 场景/步骤状态机、立绘淡入淡出、
 * 打字机、选项分支、视频、音频三通道、存档(localStorage)、输入处理 一一对应。
 *
 * 对应关系 (JS -> Qt):
 *   executeStep  -> _execute_step     nextStep   -> _next_step
 *   gotoScene    -> _goto_scene       autoAdvance-> _auto_advance
 *   showDialogue -> _show_dialogue    tickType   -> _tick_typewriter
 *   showChoice   -> _show_choice      onChoice   -> _on_choice
 *   playVideo    -> _play_video       applyBg    -> _apply_bg
 *   applyAudio   -> _apply_audio_change  placeChar-> _place_character
 *   captureState -> _capture_state    restoreState->_restore_state
 *   advance      -> _advance          (input)    -> mousePressEvent/keyPressEvent
 */
(function () {
    "use strict";

    // ---- 立绘横向锚点比例 (对齐 _POSITION_X_RATIO) ----
    const POSITION_X_RATIO = {
        left: 0.20,
        center_left: 0.36,
        center: 0.50,
        center_right: 0.64,
        right: 0.80,
    };

    const SLOT_COUNT = 9;
    const TYPEWRITER_INTERVAL = 28;   // ms (对齐 QTimer 28ms)
    const FADE_MS = 300;              // 立绘淡入淡出 (对齐 _fade_in/_out_ms)

    // ==================================================================
    // 音频管理 (对齐 AudioManager: BGM 循环 / 语音 / 音效 三通道)
    // ==================================================================
    class AudioManager {
        constructor() {
            this.bgm = new Audio();
            this.bgm.loop = true;
            this.bgm.volume = 0.6;
            this.voice = new Audio();
            this.voice.volume = 1.0;
            this.sfx = new Audio();
            this.sfx.volume = 0.9;
        }
        _play(el, url) {
            if (!url) { el.pause(); el.src = ""; return; }
            el.src = url;
            el.play().catch(() => {});  // 浏览器策略可能阻止自动播放, 忽略
        }
        playBgm(url) { this._play(this.bgm, url); }
        stopBgm() { this.bgm.pause(); this.bgm.src = ""; }
        playVoice(url) { this._play(this.voice, url); }
        stopVoice() { this.voice.pause(); this.voice.src = ""; }
        playSfx(url) { if (url) this._play(this.sfx, url); }
        stopSfx() { this.sfx.pause(); this.sfx.src = ""; }
        stopAll() { this.stopBgm(); this.stopVoice(); this.stopSfx(); }
    }

    // ==================================================================
    // 存档管理 (对齐 SaveManager: localStorage, auto + 9 槽)
    // ==================================================================
    class SaveManager {
        constructor(title) {
            this.title = title;
            this.prefix = "galpy_" + SaveManager._safe(title) + "_";
        }
        static _safe(s) {
            return (s || "game").replace(/[^\w\u4e00-\u9fa5-]/g, "_");
        }
        _autoKey() { return this.prefix + "auto"; }
        _slotKey(i) { return this.prefix + "slot_" + i; }
        hasAuto() { return localStorage.getItem(this._autoKey()) !== null; }
        saveAuto(slot) {
            if (!slot.timestamp) slot.timestamp = SaveManager._now();
            slot.title = this.title;
            localStorage.setItem(this._autoKey(), JSON.stringify(slot));
        }
        loadAuto() {
            const raw = localStorage.getItem(this._autoKey());
            return raw ? JSON.parse(raw) : null;
        }
        listSlots() {
            const out = [];
            for (let i = 1; i <= SLOT_COUNT; i++) {
                const raw = localStorage.getItem(this._slotKey(i));
                out.push(raw ? JSON.parse(raw) : null);
            }
            return out;
        }
        loadSlot(i) {
            const raw = localStorage.getItem(this._slotKey(i));
            return raw ? JSON.parse(raw) : null;
        }
        saveSlot(i, slot) {
            if (i < 1 || i > SLOT_COUNT) throw new Error("存档槽位超出范围: " + i);
            if (!slot.timestamp) slot.timestamp = SaveManager._now();
            slot.title = this.title;
            localStorage.setItem(this._slotKey(i), JSON.stringify(slot));
        }
        deleteSlot(i) { localStorage.removeItem(this._slotKey(i)); }
        static _now() {
            const d = new Date();
            const p = (n) => String(n).padStart(2, "0");
            return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
                   `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
        }
    }

    // ==================================================================
    // 主播放器
    // ==================================================================
    class GalpyPlayer {
        constructor() {
            this.project = null;
            // 运行状态 (对齐 GamePlayer.__init__)
            this.scene = null;
            this.stepIndex = -1;
            this.charEls = {};           // position -> {el, character} 当前可见/淡入中立绘
            this.bgPath = "";
            this.bgmPath = "";
            this.curCharacters = {};     // position -> 立绘相对路径 (存档用)
            this.waiting = false;
            this.videoPlaying = false;
            this.ended = false;
            this.mode = "title";         // title / playing / menu / slots

            this.fullText = "";
            this.shownText = "";
            this.textIndex = 0;
            this.typeTimer = null;

            this.audio = new AudioManager();
            this.saves = null;           // 工程加载后初始化

            this._cacheDom();
            this._bindEvents();
        }

        // ---- DOM 缓存 ----
        _cacheDom() {
            const $ = (id) => document.getElementById(id);
            this.el = {
                root: $("game-root"),
                bg: $("bg-layer"),
                charLayer: $("char-layer"),
                video: $("video-layer"),
                dialogue: $("dialogue-box"),
                namePlate: $("name-plate"),
                bodyText: $("body-text"),
                hint: $("hint-text"),
                prompt: $("prompt-label"),
                choices: $("choices-widget"),
                quickSave: $("quick-save-btn"),
                title: $("title-widget"),
                menu: $("menu-widget"),
                slot: $("slot-widget"),
                slotHeader: $("slot-header"),
                slotGrid: $("slot-grid"),
                end: $("end-widget"),
                endSub: $("end-sub"),
                titleLabel: $("title-label"),
                loading: $("loading"),
            };
        }

        // ---- 启动: 加载工程 ----
        async start() {
            // 项目数据 URL 与资源前缀由页面注入 (dev 用 /api/project + /assets/,
            // 静态打包用 project.json + 空前缀), 兼容两种部署形态
            const projectUrl = window.GALPY_PROJECT_URL || "/api/project";
            try {
                const resp = await fetch(projectUrl);
                this.project = await resp.json();
            } catch (e) {
                this.el.loading.innerHTML =
                    '<div class="loading-text" style="color:#ff9a9a">工程加载失败: ' +
                    e.message + "</div>";
                return;
            }
            this.saves = new SaveManager(this.project.title || "GalPy");
            document.title = (this.project.title || "GalPy") + " - GalPy Web";
            this.el.loading.classList.add("hidden");
            this._showTitleMenu();
        }

        // ==============================================================
        // 资源 URL (工程内相对路径 -> /assets/<path>)
        // ==============================================================
        assetUrl(relPath) {
            if (!relPath) return "";
            // 资源前缀由页面注入: dev="/assets/" (路由 /assets/<path> 服务 base_dir),
            // 静态打包="" (relPath 即相对 index.html 的路径)。
            // relPath 形如 "assets/backgrounds/bg.png", 分段编码后拼接。
            const prefix = window.GALPY_ASSET_PREFIX != null ? window.GALPY_ASSET_PREFIX : "/assets/";
            return prefix + relPath.split("/").map(encodeURIComponent).join("/");
        }

        // ==============================================================
        // 标题菜单 (对齐 _show_title_menu)
        // ==============================================================
        _showTitleMenu() {
            this.mode = "title";
            this.ended = false;
            this.waiting = false;
            this.videoPlaying = false;
            this._stopTypewriter();
            this.audio.stopAll();
            this._hideAllOverlays();

            const cover = this._coverScene();
            if (cover) {
                this.bgPath = cover.background || "";
                this._applyBg(this.bgPath);
                this.bgmPath = cover.bgm || "";
                if (cover.bgm) this.audio.playBgm(this.assetUrl(cover.bgm));
                this.el.titleLabel.textContent = cover.name || this.project.title || "GalPy";
            } else {
                this.bgPath = "";
                this._applyBg("");
                this.bgmPath = "";
                this.el.titleLabel.textContent = this.project.title || "GalPy";
            }
            // 继续游戏按钮: 仅当存在自动存档时可用
            const contBtn = this.el.title.querySelector('[data-act="continue"]');
            contBtn.disabled = !this.saves.hasAuto();
            this.el.quickSave.classList.add("hidden");
            this.el.title.classList.remove("hidden");
        }

        _startNewGame() {
            // 对齐 _start_new_game: 跳过封面, 进入起始场景
            this._hideAllOverlays();
            this.mode = "playing";
            this.ended = false;
            this.waiting = false;
            this.bgPath = "";
            this.bgmPath = "";
            this.curCharacters = {};
            this._clearCharacters();
            this.audio.stopAll();
            const cover = this._coverScene();
            let startId = this.project.start_scene || "";
            if (!startId || (cover && startId === cover.id)) {
                const first = this.project.scenes.find((s) => !s.is_cover);
                startId = first ? first.id : "";
            }
            if (startId && this._getScene(startId)) {
                this._gotoScene(startId);
                this.el.quickSave.classList.remove("hidden");
            } else {
                this._showEnd();
            }
        }

        _continueGame() {
            const slot = this.saves.loadAuto();
            if (!slot) {
                this._toast("没有找到上次的自动存档。");
                return;
            }
            this._hideAllOverlays();
            this._restoreState(slot);
        }

        // ==============================================================
        // 系统菜单 (对齐 _show_system_menu / _resume_game / _back_to_title)
        // ==============================================================
        _showSystemMenu() {
            if (this.ended) return;
            this.mode = "menu";
            this._stopTypewriter();
            this.audio.stopVoice();
            this.el.quickSave.classList.add("hidden");
            this.el.menu.classList.remove("hidden");
        }
        _resumeGame() {
            this.el.menu.classList.add("hidden");
            this.mode = "playing";
            this.el.quickSave.classList.remove("hidden");
            if (this.waiting && this.textIndex < this.fullText.length) {
                this._startTypewriter();
            }
        }
        _backToTitle() {
            this._autoSave();
            this.el.menu.classList.add("hidden");
            this._showTitleMenu();
        }

        // ==============================================================
        // 存档槽 (对齐 _show_slots / _refresh_slot_buttons / _on_slot_clicked)
        // ==============================================================
        _showSlots(mode, returnTo) {
            this._slotMode = mode;
            this._slotReturn = returnTo;
            this.el.slotHeader.textContent = mode === "save" ? "保存进度" : "读取进度";
            this._refreshSlots();
            if (returnTo === "title") this.el.title.classList.add("hidden");
            else if (returnTo === "menu") this.el.menu.classList.add("hidden");
            this.el.quickSave.classList.add("hidden");
            this.mode = "slots";
            this.el.slot.classList.remove("hidden");
        }
        _refreshSlots() {
            const slots = this.saves.listSlots();
            this.el.slotGrid.innerHTML = "";
            for (let i = 0; i < SLOT_COUNT; i++) {
                const sl = slots[i];
                const btn = document.createElement("button");
                btn.className = "slot-btn";
                if (sl === null) {
                    btn.textContent = `槽位 ${i + 1}\n— 空 —`;
                } else {
                    btn.textContent =
                        `槽位 ${i + 1}\n${sl.label || "(无描述)"}\n${sl.timestamp}`;
                    const del = document.createElement("span");
                    del.className = "slot-delete";
                    del.textContent = "删除";
                    del.onclick = (ev) => { ev.stopPropagation(); this._deleteSlot(i + 1); };
                    btn.appendChild(del);
                }
                btn.onclick = () => this._onSlotClicked(i + 1);
                this.el.slotGrid.appendChild(btn);
            }
        }
        _onSlotClicked(index) {
            if (this._slotMode === "save") {
                const slot = this._captureState();
                try {
                    this.saves.saveSlot(index, slot);
                } catch (e) {
                    this._toast("保存失败: " + e.message);
                    return;
                }
                this._refreshSlots();
                this._toast("已保存到槽位 " + index + "。");
                this._closeSlots();
            } else {
                const slot = this.saves.loadSlot(index);
                if (!slot) { this._toast("槽位 " + index + " 没有存档。"); return; }
                this.el.slot.classList.add("hidden");
                this._restoreState(slot);
            }
        }
        _deleteSlot(index) {
            if (!confirm("确定删除槽位 " + index + " 的存档吗?")) return;
            this.saves.deleteSlot(index);
            this._refreshSlots();
        }
        _closeSlots() {
            this.el.slot.classList.add("hidden");
            const ret = this._slotReturn || "menu";
            if (ret === "title" || !this.scene) {
                this._showTitleMenu();
            } else if (ret === "playing") {
                this.mode = "playing";
                this.el.quickSave.classList.remove("hidden");
                if (this.waiting && this.textIndex < this.fullText.length) {
                    this._startTypewriter();
                }
            } else {
                this.mode = "menu";
                this.el.menu.classList.remove("hidden");
            }
        }

        // ==============================================================
        // 存档: 捕获 / 恢复 (对齐 _capture_state / _restore_state)
        // ==============================================================
        _saveLabel() {
            if (!this.scene) return "";
            if (this.stepIndex >= 0 && this.stepIndex < this.scene.steps.length) {
                return `${this.scene.name}  #${this.stepIndex + 1}`;
            }
            return this.scene.name;
        }
        _captureState() {
            return {
                scene_id: this.scene ? this.scene.id : "",
                step_index: Math.max(0, this.stepIndex),
                background: this.bgPath,
                bgm: this.bgmPath,
                characters: Object.fromEntries(
                    Object.entries(this.curCharacters).filter(([, v]) => v)
                ),
                timestamp: "",
                label: this._saveLabel(),
                title: this.project.title,
            };
        }
        _autoSave() {
            if (this.mode !== "playing" || !this.scene || this.stepIndex < 0) return;
            try { this.saves.saveAuto(this._captureState()); } catch (e) { /* 忽略 */ }
        }
        _restoreState(slot) {
            const scene = this._getScene(slot.scene_id);
            if (!scene) {
                this._toast("存档指向的场景已不存在。");
                this._showTitleMenu();
                return;
            }
            this.scene = scene;
            this.stepIndex = Math.max(0, slot.step_index);
            this.ended = false;
            this.videoPlaying = false;

            // 恢复背景
            this.bgPath = slot.background || "";
            this._applyBg(this.bgPath);

            // 恢复立绘 (直接显示, 不带淡入)
            this._clearCharacters();
            this.curCharacters = {};
            for (const [pos, rel] of Object.entries(slot.characters || {})) {
                if (!rel) continue;
                this.curCharacters[pos] = rel;
                this._addCharEl(pos, rel, 1.0);
            }
            // 恢复 BGM
            this.bgmPath = slot.bgm || "";
            this.audio.stopAll();
            if (slot.bgm) this.audio.playBgm(this.assetUrl(slot.bgm));

            this._hideAllOverlays();
            this.mode = "playing";
            this.el.quickSave.classList.remove("hidden");
            this.el.dialogue.classList.add("hidden");
            this.el.choices.classList.add("hidden");
            this.el.prompt.classList.add("hidden");
            this.el.video.classList.remove("show");
            this.el.video.pause();

            // 重新执行当前步骤
            if (this.stepIndex >= 0 && this.stepIndex < scene.steps.length) {
                this._executeStep(scene.steps[this.stepIndex]);
            } else {
                this._nextStep();
            }
        }

        // ==============================================================
        // 流程推进 (对齐 _goto_scene / _next_step / _execute_step / _auto_advance)
        // ==============================================================
        _getScene(id) { return this.project.scenes.find((s) => s.id === id) || null; }
        _sceneIndex(id) { return this.project.scenes.findIndex((s) => s.id === id); }
        _coverScene() { return this.project.scenes.find((s) => s.is_cover) || null; }

        _gotoScene(sceneId) {
            const scene = this._getScene(sceneId);
            if (!scene) { this._showEnd(); return; }
            this.scene = scene;
            this.stepIndex = -1;
            if (scene.background) this._applyBg(scene.background);
            if (scene.bgm) this._applyBgm(scene.bgm);
            this._nextStep();
        }
        _nextStep() {
            if (this.ended || !this.scene) return;
            this.stepIndex++;
            const steps = this.scene.steps;
            if (this.stepIndex >= steps.length) {
                // 场景走完: 跳过分支场景, 进入下一个顶级场景; 否则结束
                const idx = this._sceneIndex(this.scene.id);
                let nxt = null;
                for (let i = idx + 1; i < this.project.scenes.length; i++) {
                    if (!this.project.scenes[i].parent_scene) {
                        nxt = this.project.scenes[i];
                        break;
                    }
                }
                if (nxt) this._gotoScene(nxt.id);
                else this._showEnd();
                return;
            }
            this._executeStep(steps[this.stepIndex]);
        }
        _autoAdvance() {
            // 非交互步骤立即推进 (用 setTimeout(0) 避免深递归, 对齐 QTimer.singleShot(0))
            setTimeout(() => this._nextStep(), 0);
        }
        _executeStep(step) {
            const t = step.type;
            if (t === "dialogue") this._showDialogue(step, false);
            else if (t === "narration") this._showDialogue(step, true);
            else if (t === "choice") this._showChoice(step);
            else if (t === "video") this._playVideo(step);
            else if (t === "bg_change") { this._applyBg(step.background); this._autoAdvance(); }
            else if (t === "audio_change") { this._applyAudioChange(step); this._autoAdvance(); }
            else if (t === "character_exit") { this._applyCharacterExit(step); this._autoAdvance(); }
            else if (t === "goto") this._gotoScene(step.next);
            else if (t === "end") this._showEnd();
        }

        // ==============================================================
        // 媒体应用 (对齐 _apply_bg / _apply_bgm / _play_sfx / _apply_audio_change)
        // ==============================================================
        _applyBg(relPath) {
            this.bgPath = relPath || "";
            if (relPath) {
                this.el.bg.style.backgroundImage = `url("${this.assetUrl(relPath)}")`;
            } else {
                this.el.bg.style.backgroundImage = "";
            }
        }
        _applyBgm(relPath) {
            this.bgmPath = relPath || "";
            this.audio.playBgm(this.assetUrl(relPath));
        }
        _applyAudioChange(step) {
            const cat = step.audio_category || "bgm";
            const act = step.audio_action || "play";
            if (cat === "bgm") {
                if (act === "stop") { this.audio.stopBgm(); this.bgmPath = ""; }
                else { this.bgmPath = step.audio_file || ""; this.audio.playBgm(this.assetUrl(step.audio_file)); }
            } else if (cat === "sfx") {
                if (act === "stop") this.audio.stopSfx();
                else this.audio.playSfx(this.assetUrl(step.audio_file));
            } else if (cat === "voice") {
                if (act === "stop") this.audio.stopVoice();
                else this.audio.playVoice(this.assetUrl(step.audio_file));
            }
        }

        // ==============================================================
        // 立绘 (对齐 _place_character / _apply_character_exit / _tick_animation)
        // 用 CSS transition 代替手动 alpha tick
        // ==============================================================
        _addCharEl(position, relPath, opacity) {
            const el = document.createElement("img");
            el.className = "char-sprite";
            el.src = this.assetUrl(relPath);
            el.dataset.position = position;
            const ratio = POSITION_X_RATIO[position] != null ? POSITION_X_RATIO[position] : 0.5;
            el.style.left = (ratio * 100) + "%";
            el.style.opacity = opacity;
            this.el.charLayer.appendChild(el);
            this.charEls[position] = { el, character: relPath };
            return el;
        }
        _placeCharacter(relPath, position) {
            const existing = this.charEls[position];
            if (existing && existing.character === relPath) {
                // 同角色同位置: 只刷新图 (表情切换), 不重新淡入
                existing.el.src = this.assetUrl(relPath);
                existing.character = relPath;
                return;
            }
            // 同角色在其他位置: 旧位置淡出 (角色"移动")
            for (const [pos, info] of Object.entries(this.charEls)) {
                if (pos !== position && info.character === relPath) {
                    this._fadeoutRemove(info.el);
                    delete this.charEls[pos];
                    delete this.curCharacters[pos];
                }
            }
            // 该位置上的旧不同角色: 淡出
            if (existing) {
                this._fadeoutRemove(existing.el);
                delete this.charEls[position];
                delete this.curCharacters[position];
            }
            // 新立绘淡入
            this._addCharEl(position, relPath, 0);
            this.curCharacters[position] = relPath;
            // 下一帧触发淡入 (让 opacity 过渡生效)
            requestAnimationFrame(() => {
                const info = this.charEls[position];
                if (info) info.el.style.opacity = "1";
            });
        }
        _fadeoutRemove(el) {
            el.style.opacity = "0";
            setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, FADE_MS);
        }
        _clearCharacters() {
            for (const info of Object.values(this.charEls)) {
                if (info.el.parentNode) info.el.parentNode.removeChild(info.el);
            }
            this.charEls = {};
        }
        _applyCharacterExit(step) {
            if (step.exit_character) {
                // 清除指定角色: 扫描所有位置, 命中即淡出
                for (const [pos, info] of Object.entries(this.charEls)) {
                    if (info.character === step.exit_character) {
                        this._fadeoutRemove(info.el);
                        delete this.charEls[pos];
                        delete this.curCharacters[pos];
                    }
                }
            } else {
                const pos = step.exit_position || "all";
                if (pos === "all") {
                    for (const info of Object.values(this.charEls)) this._fadeoutRemove(info.el);
                    this.charEls = {};
                    this.curCharacters = {};
                } else {
                    const info = this.charEls[pos];
                    if (info) {
                        this._fadeoutRemove(info.el);
                        delete this.charEls[pos];
                        delete this.curCharacters[pos];
                    }
                }
            }
        }

        // ==============================================================
        // 对白 / 旁白 (对齐 _show_dialogue / _tick_typewriter)
        // ==============================================================
        _showDialogue(step, narration) {
            if (step.character) {
                const pos = POSITION_X_RATIO[step.position] != null ? step.position : "left";
                this._placeCharacter(step.character, pos);
            }
            // 语音
            this.audio.playVoice(this.assetUrl(step.voice));
            // 名牌
            if (narration || !step.speaker) {
                this.el.namePlate.classList.add("hidden");
            } else {
                this.el.namePlate.textContent = step.speaker;
                this.el.namePlate.classList.remove("hidden");
            }
            // 文字 + 打字机
            this.fullText = step.text || "";
            this.shownText = "";
            this.textIndex = 0;
            this.el.bodyText.textContent = "";
            this.el.dialogue.classList.remove("hidden");
            this.el.dialogue.style.zIndex = "10";
            this.waiting = true;
            if (this.fullText) {
                this.el.hint.classList.add("hidden");
                this._startTypewriter();
            } else {
                this.el.hint.classList.remove("hidden");
            }
            this._autoSave();
        }
        _startTypewriter() {
            this._stopTypewriter();
            this.typeTimer = setInterval(() => this._tickTypewriter(), TYPEWRITER_INTERVAL);
        }
        _stopTypewriter() {
            if (this.typeTimer) { clearInterval(this.typeTimer); this.typeTimer = null; }
        }
        _tickTypewriter() {
            if (this.textIndex < this.fullText.length) {
                this.shownText += this.fullText[this.textIndex];
                this.textIndex++;
                this.el.bodyText.textContent = this.shownText;
            } else {
                this._stopTypewriter();
            }
        }

        // ==============================================================
        // 选项分支 (对齐 _show_choice / _on_choice)
        // ==============================================================
        _showChoice(step) {
            this.el.dialogue.classList.add("hidden");
            this.el.choices.innerHTML = "";
            if (step.prompt) {
                this.el.prompt.textContent = step.prompt;
                this.el.prompt.classList.remove("hidden");
            } else {
                this.el.prompt.classList.add("hidden");
            }
            for (const opt of (step.options || [])) {
                const btn = document.createElement("button");
                btn.className = "choice-btn";
                btn.textContent = opt.text || "(空选项)";
                btn.onclick = () => this._onChoice(opt.next);
                this.el.choices.appendChild(btn);
            }
            this.el.choices.classList.remove("hidden");
            this._autoSave();
        }
        _onChoice(nextId) {
            this.el.choices.classList.add("hidden");
            this.el.prompt.classList.add("hidden");
            if (nextId) this._gotoScene(nextId);
            else this._nextStep();
        }

        // ==============================================================
        // 视频 (对齐 _play_video / _on_video_status / _stop_video)
        // ==============================================================
        _playVideo(step) {
            const url = this.assetUrl(step.source);
            if (!step.source || !url) { this._autoAdvance(); return; }
            this.videoPlaying = true;
            const v = this.el.video;
            v.classList.add("show");
            v.src = url;
            v.play().catch(() => {});
            const finish = () => {
                this._stopVideo();
                this._nextStep();
            };
            v.onended = finish;
            // 视频缺失 / 解码失败时跳过, 避免流程卡住
            v.onerror = finish;
        }
        _stopVideo() {
            const v = this.el.video;
            v.pause();
            v.removeAttribute("src");
            v.load();
            v.classList.remove("show");
            v.onended = null;
            this.videoPlaying = false;
        }

        // ==============================================================
        // 结束 (对齐 _show_end / _on_end_close)
        // ==============================================================
        _showEnd() {
            this.ended = true;
            this.waiting = false;
            this.videoPlaying = false;
            this.mode = "title";
            this._stopTypewriter();
            this._clearCharacters();
            this.bgPath = "";
            this.bgmPath = "";
            this.curCharacters = {};
            this.el.dialogue.classList.add("hidden");
            this.el.choices.classList.add("hidden");
            this.el.prompt.classList.add("hidden");
            this.el.video.classList.remove("show");
            this.el.video.pause();
            this.el.quickSave.classList.add("hidden");
            this.audio.stopAll();
            this._applyBg("");
            this.el.endSub.textContent = `《${this.project.title}》`;
            this.el.end.classList.remove("hidden");
        }
        _onEndClose() {
            this.el.end.classList.add("hidden");
            this._showTitleMenu();
        }

        // ==============================================================
        // 用户输入 (对齐 _advance / mousePressEvent / keyPressEvent)
        // ==============================================================
        _advance() {
            if (this.mode !== "playing") return;
            if (this.ended) return;
            if (this.videoPlaying) { this._stopVideo(); this._nextStep(); return; }
            if (!this.waiting) return;  // 正在显示选项, 必须点击具体选项
            if (this.typeTimer) {
                // 立即显示完整文字
                this._stopTypewriter();
                this.shownText = this.fullText;
                this.textIndex = this.fullText.length;
                this.el.bodyText.textContent = this.shownText;
                this.el.hint.classList.remove("hidden");
                return;
            }
            this.waiting = false;
            this.audio.stopVoice();
            this.el.hint.classList.add("hidden");
            this._nextStep();
        }

        _bindEvents() {
            // 点击推进 (对齐 mousePressEvent: 仅 playing 模式)
            this.el.root.addEventListener("click", (ev) => {
                // 点击覆盖层按钮 / 选项按钮 / 存档按钮 不触发推进
                const t = ev.target;
                if (t.closest("button")) return;
                if (this.mode !== "playing") return;
                this._advance();
            });
            // 键盘 (对齐 keyPressEvent)
            document.addEventListener("keydown", (ev) => {
                const k = ev.key;
                if (k === "Escape") {
                    if (this.mode === "playing") this._showSystemMenu();
                    else if (this.mode === "menu") this._resumeGame();
                    else if (this.mode === "slots") this._closeSlots();
                    return;
                }
                if (this.mode !== "playing") return;
                if (k === "Enter" || k === " " || k === "Spacebar") {
                    ev.preventDefault();
                    this._advance();
                }
            });

            // 标题菜单按钮
            this.el.title.addEventListener("click", (ev) => {
                const btn = ev.target.closest("[data-act]");
                if (!btn) return;
                const act = btn.dataset.act;
                if (act === "new-game") this._startNewGame();
                else if (act === "continue") this._continueGame();
                else if (act === "load") this._showSlots("load", "title");
            });
            // 系统菜单按钮
            this.el.menu.addEventListener("click", (ev) => {
                const btn = ev.target.closest("[data-act]");
                if (!btn) return;
                const act = btn.dataset.act;
                if (act === "save") this._showSlots("save", "menu");
                else if (act === "load-menu") this._showSlots("load", "menu");
                else if (act === "title") this._backToTitle();
                else if (act === "resume") this._resumeGame();
            });
            // 存档槽返回
            this.el.slot.addEventListener("click", (ev) => {
                const btn = ev.target.closest('[data-act="slot-back"]');
                if (btn) this._closeSlots();
            });
            // 结束页
            this.el.end.addEventListener("click", (ev) => {
                const btn = ev.target.closest('[data-act="end-close"]');
                if (btn) this._onEndClose();
            });
            // 浮动存档按钮
            this.el.quickSave.addEventListener("click", () => {
                if (this.mode === "playing") this._showSlots("save", "playing");
            });

            // 首次用户交互后解锁音频自动播放 (浏览器策略要求在用户手势内播放)
            const unlock = () => {
                if (this.bgmPath) {
                    this.audio.playBgm(this.assetUrl(this.bgmPath));
                } else {
                    this.audio.bgm.play().catch(() => {});
                }
                document.removeEventListener("click", unlock);
                document.removeEventListener("keydown", unlock);
            };
            document.addEventListener("click", unlock);
            document.addEventListener("keydown", unlock);
        }

        // ==============================================================
        // 工具
        // ==============================================================
        _hideAllOverlays() {
            for (const el of [this.el.title, this.el.menu, this.el.slot, this.el.end]) {
                el.classList.add("hidden");
            }
            this.el.quickSave.classList.add("hidden");
        }
        _toast(msg) {
            // 简易提示 (替代 QMessageBox)
            const t = document.createElement("div");
            t.textContent = msg;
            t.style.cssText =
                "position:fixed;left:50%;top:20%;transform:translateX(-50%);" +
                "background:rgba(20,24,40,0.95);color:#fff;padding:12px 24px;" +
                "border-radius:8px;border:1px solid #5577bb;z-index:9999;" +
                "font-size:15px;max-width:80%;text-align:center;";
            document.body.appendChild(t);
            setTimeout(() => { if (t.parentNode) t.parentNode.removeChild(t); }, 2200);
        }
    }

    // ---- 启动 ----
    window.addEventListener("DOMContentLoaded", () => {
        const player = new GalpyPlayer();
        player.start();
        window._galpyPlayer = player;  // 调试用
    });
})();
