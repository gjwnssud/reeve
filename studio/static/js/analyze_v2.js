/**
 * Reeve - 고급 차량 이미지 분석
 * 차량 감지, 드래그 가능한 바운딩 박스, 다중 이미지 처리, SSE 스트리밍
 */

const API_BASE = '';
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const imageGridFile = document.getElementById('imageGridFile');
const imageGridFolder = document.getElementById('imageGridFolder');

// UUID 관리 (브라우저별 다중 사용자 구분)
function getClientUUID() {
    let uuid = localStorage.getItem('reeve_client_uuid');
    if (!uuid) {
        uuid = crypto.randomUUID();
        localStorage.setItem('reeve_client_uuid', uuid);
    }
    return uuid;
}
const CLIENT_UUID = getClientUUID();

// 전역 상태
// status 값: uploading, detecting, detected, no_vehicle, detection_error, analyzing, completed, analysis_error
const state = {
    images: new Map(), // imageId -> { file, analyzedId, originalImagePath, source, detections, selectedBbox, status, result }
    // 이벤트 카운터 (localStorage 백업, 증가만 — 감소 없음)
    fileStats: JSON.parse(localStorage.getItem(`reeve_file_stats_${CLIENT_UUID}`))
        || { uploaded: 0, detected: 0, detectionFailed: 0, analyzed: 0, analysisError: 0, manuallyEdited: 0 },
    folderStats: JSON.parse(localStorage.getItem(`reeve_folder_stats_${CLIENT_UUID}`))
        || { uploaded: 0, detected: 0, detectionFailed: 0, analyzed: 0, analysisError: 0 },
    hydrateState: {
        file:   { loading: false, page: 0, pageSize: 9, totalCount: 0 },
        folder: { loading: false, page: 0, pageSize: 9, totalCount: 0 }
    }
};

// 폴더 감시 상태 (File System Access API)
const folderWatch = {
    dirHandle: null,    // FileSystemDirectoryHandle
    intervalId: null,   // setInterval ID
    seen: new Set(),    // 이미 큐에 추가(또는 무시)한 파일명
    queue: [],          // { name, handle } — 처리 대기 중인 파일
    isProcessing: false,
    total: 0,           // 발견된 전체 파일 수
    processed: 0,       // 처리 완료된 파일 수
};

// 동시성 제한 세마포어 (차량 감지 요청 동시 최대 4개)
const MAX_CONCURRENT_DETECTIONS = 4;
class Semaphore {
    constructor(max) {
        this.max = max;
        this.current = 0;
        this.queue = [];
    }
    acquire() {
        return new Promise(resolve => {
            if (this.current < this.max) {
                this.current++;
                resolve();
            } else {
                this.queue.push(resolve);
            }
        });
    }
    release() {
        this.current--;
        if (this.queue.length > 0) {
            this.current++;
            this.queue.shift()();
        }
    }
}
const detectionSemaphore = new Semaphore(MAX_CONCURRENT_DETECTIONS);

//=============================================================================
// 초기화
//=============================================================================

uploadArea.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => {
    handleFiles(Array.from(e.target.files));  // Array로 변환 후 전달 (FileList는 live 객체라 value='' 초기화 시 비워짐)
    fileInput.value = '';  // 같은 파일 재선택 및 연속 업로드 허용
});

// 드래그 앤 드롭
uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragging');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragging');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragging');
    handleFiles(e.dataTransfer.files);
});

// 화면 크기 변경 시 바운딩 박스 재조정
let resizeTimeout;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        // 모든 이미지의 바운딩 박스 재조정
        state.images.forEach((imageState, imageId) => {
            if (imageState.selectedBbox) {
                createBboxOverlay(imageId, imageState.selectedBbox);
            }
        });
    }, 250); // 250ms 디바운스
});

//=============================================================================
// 파일 처리
//=============================================================================

async function handleFiles(files, { onEachUploadSuccess, source = 'file' } = {}) {
    for (const file of files) {
        if (!file.type.startsWith('image/')) {
            showToast('이미지 파일만 업로드 가능합니다', 'error');
            continue;
        }

        if (file.size > 5 * 1024 * 1024) {
            showToast(`${file.name}: 파일 크기가 5MB를 초과합니다`, 'error');
            continue;
        }

        const imageId = 'img_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

        // 상태 저장
        const imageState = {
            file,
            analyzedId: null,          // DB 레코드 ID (즉시 업로드 후 설정)
            originalImagePath: null,   // 서버 원본 파일 경로
            source,                    // 'file' | 'folder'
            detections: [],
            selectedBbox: null,
            status: 'uploading',
            result: null
        };
        state.images.set(imageId, imageState);

        renderStats();

        // 서버에 즉시 업로드 → DB 레코드 생성
        let uploadSuccess = false;
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('source', imageState.source);
            formData.append('client_uuid', CLIENT_UUID);
            const resp = await fetch('/api/upload', { method: 'POST', body: formData });
            if (resp.ok) {
                const { analyzed_id, original_image_path } = await resp.json();
                imageState.analyzedId = analyzed_id;
                imageState.originalImagePath = original_image_path;
                uploadSuccess = true;
                incrementStat(source, 'uploaded');
                // 페이지네이션 카운트 증가 (라이브 카드는 그리드에 직접 추가되므로 컨트롤만 갱신)
                state.hydrateState[source].totalCount++;
                renderPagination(source);
            }
        } catch (e) {
            console.warn('즉시 업로드 실패 (하위 호환 모드):', e);
        }

        // 업로드 성공 콜백 (폴더 감시: 로컬 파일 삭제에 사용)
        if (uploadSuccess && onEachUploadSuccess) {
            await onEachUploadSuccess(file).catch(e => console.warn('업로드 후 콜백 실패:', e));
        }

        // UI 생성 (YOLO는 createImageCard 내부에서 자동 실행)
        await createImageCard(imageId, file);
    }
}

//=============================================================================
// UI 생성
//=============================================================================

async function createImageCard(imageId, file) {
    const card = document.createElement('div');
    card.className = 'col';
    card.id = `image-${imageId}`;

    // 먼저 빈 카드 추가
    card.innerHTML = `
        <div class="card shadow-sm overflow-hidden">
        <div class="image-container">
            <img id="img-${imageId}" alt="${file.name}" style="display:none;">
            <canvas id="canvas-${imageId}" class="image-canvas" style="display:none;"></canvas>
            <div id="bbox-overlay-${imageId}"></div>
        </div>
        <div class="card-body">
            <h6 class="d-flex align-items-center gap-2">
                ${file.name}
                <span class="badge rounded-pill bg-warning" id="status-${imageId}">업로드 중</span>
            </h6>
            <div id="detection-list-${imageId}" class="list-group list-group-flush my-2"></div>
            <div id="result-${imageId}" class="card bg-body-secondary p-3 mt-2" style="display: none;"></div>
            <div class="d-flex gap-2 mt-3 flex-wrap">
                <button class="btn btn-sm btn-primary" id="analyze-btn-${imageId}" disabled>
                    분석하기
                </button>
                <button class="btn btn-sm btn-success" id="edit-btn-${imageId}" style="display:none;" onclick="openAnalysisEditModal('${imageId}')">
                    분석결과 수정
                </button>
                <button class="btn btn-sm btn-primary" id="save-btn-${imageId}" style="display:none;" onclick="saveImageToVectorDB('${imageId}')">
                    저장
                </button>
                <button class="btn btn-sm btn-danger" onclick="removeImage('${imageId}')">
                    삭제
                </button>
            </div>
            <div class="progress mt-3" style="display: none; height: 4px;" id="progress-${imageId}">
                <div class="progress-bar" role="progressbar" style="width: 0%; background: linear-gradient(90deg, #667eea, #764ba2);"></div>
            </div>
        </div>
        </div>
    `;

    const targetGrid = (state.images.get(imageId)?.source === 'folder') ? imageGridFolder : imageGridFile;
    targetGrid.insertBefore(card, targetGrid.firstChild);

    // 이미지 로드
    const img = document.getElementById(`img-${imageId}`);
    const canvas = document.getElementById(`canvas-${imageId}`);

    const startImageLoad = (src) => {
        img.src = src;
        img.onload = () => {
            // 이미지 표시
            img.style.display = 'block';
            canvas.style.display = 'block';

            // 캔버스 초기화 (한 번만)
            const container = img.parentElement;
            canvas.width = img.clientWidth;
            canvas.height = img.clientHeight;

            // 이미지 크기 변경 감지 (ResizeObserver)
            const resizeObserver = new ResizeObserver(() => {
                const imageState = state.images.get(imageId);
                if (imageState && imageState.selectedBbox) {
                    // 바운딩 박스 재조정
                    createBboxOverlay(imageId, imageState.selectedBbox);
                }
            });
            resizeObserver.observe(img);

            // 차량 감지 시작
            detectVehicle(imageId);
        };
    };

    // 서버에 업로드된 원본 경로가 있으면 서버 URL 사용 (로컬 파일 삭제 후에도 동작)
    // 없으면 FileReader로 로컬 파일 읽기 (일반 파일 업로드 경로)
    const curState = state.images.get(imageId);
    if (curState && curState.originalImagePath) {
        startImageLoad('/' + curState.originalImagePath);
    } else {
        const reader = new FileReader();
        reader.onload = (e) => startImageLoad(e.target.result);
        reader.readAsDataURL(file);
    }
}

//=============================================================================
// 차량 감지
//=============================================================================

async function detectVehicle(imageId) {
    const imageState = state.images.get(imageId);
    if (!imageState) return;

    const displayName = imageState.file ? imageState.file.name : `ID:${imageState.analyzedId}`;

    updateStatus(imageId, 'detecting', '대기 중...');

    // 세마포어로 동시 요청 수 제한
    await detectionSemaphore.acquire();
    updateStatus(imageId, 'detecting', '차량 감지 중');

    const formData = new FormData();
    if (imageState.analyzedId) {
        formData.append('analyzed_id', imageState.analyzedId);
    } else {
        formData.append('file', imageState.file);  // 하위 호환
    }

    try {
        const response = await fetch(`${API_BASE}/api/detect-vehicle`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }

        const data = await response.json();

        const current = state.images.get(imageId);
        if (!current) return;

        current.detections = data.detections;

        // 감지 결과 표시
        displayDetections(imageId, data.detections);

        if (data.detections.length > 0) {
            // 자동으로 첫 번째 차량 선택
            selectDetection(imageId, 0);
            current.status = 'detected';
            updateStatus(imageId, 'detected', `차량 ${data.detections.length}대 감지`);
            incrementStat(current.source, 'detected');
            showToast(`${displayName}: 차량 ${data.detections.length}대 감지됨`);

            // 폴더 감시 모드: YOLO 감지 성공 시 자동 분석
            if (current.source === 'folder') {
                analyzeImageSimple(imageId, current);
            }
        } else {
            // 차량이 감지되지 않은 경우 - 감지 실패로 분류
            current.status = 'no_vehicle';
            incrementStat(current.source, 'detectionFailed');
            updateStatus(imageId, 'error', '차량 미감지');
            showToast(`${displayName}: 차량이 감지되지 않았습니다`, 'error');
        }

        renderStats();

    } catch (error) {
        console.error('Detection error:', error);
        updateStatus(imageId, 'error', '감지 실패');
        const current = state.images.get(imageId);
        if (current) {
            current.status = 'detection_error';
            incrementStat(current.source, 'detectionFailed');
        }
        renderStats();
        showToast(`${displayName}: 차량 감지 실패 - ${error.message}`, 'error');
    } finally {
        detectionSemaphore.release();
    }
}

function displayDetections(imageId, detections) {
    const listContainer = document.getElementById(`detection-list-${imageId}`);
    const analyzeBtn = document.getElementById(`analyze-btn-${imageId}`);

    if (!detections || detections.length === 0) {
        listContainer.innerHTML = `<p style="color: #999; font-size: 13px;">차량이 감지되지 않았습니다. 이미지 위에서 드래그하여 영역을 지정하세요.</p>`;
        // YOLO 미감지 → 자동으로 드래그 그리기 모드 진입
        enableManualDraw(imageId);
        return;
    }

    listContainer.innerHTML = detections.map((det, idx) => `
        <div class="list-group-item list-group-item-action" id="detection-${imageId}-${idx}" onclick="selectDetection('${imageId}', ${idx})">
            <strong>${det.class_name}</strong> (신뢰도: ${(det.confidence * 100).toFixed(1)}%)
        </div>
    `).join('');

    // 분석 버튼 활성화
    if (analyzeBtn) {
        analyzeBtn.disabled = false;
        analyzeBtn.onclick = () => analyzeVehicle(imageId);
    }

    // 캔버스에 모든 박스 그리기
    drawAllBboxes(imageId, detections);
}

function drawAllBboxes(imageId, detections) {
    const canvas = document.getElementById(`canvas-${imageId}`);
    const img = document.getElementById(`img-${imageId}`);

    if (!canvas || !img || !img.naturalWidth) return;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const scaleX = canvas.width / img.naturalWidth;
    const scaleY = canvas.height / img.naturalHeight;

    detections.forEach((det, idx) => {
        const [x1, y1, x2, y2] = det.bbox;
        const sx1 = x1 * scaleX;
        const sy1 = y1 * scaleY;
        const sx2 = x2 * scaleX;
        const sy2 = y2 * scaleY;

        ctx.strokeStyle = '#00ff00';
        ctx.lineWidth = 2;
        ctx.strokeRect(sx1, sy1, sx2 - sx1, sy2 - sy1);

        // 레이블
        ctx.fillStyle = '#00ff00';
        ctx.font = 'bold 12px Arial';
        const label = `${det.class_name} ${(det.confidence * 100).toFixed(0)}%`;
        ctx.fillText(label, sx1 + 5, sy1 + 15);
    });
}

// 수동 그리기 모드 AbortController (중복 리스너 방지)
const manualDrawControllers = new Map(); // imageId → AbortController

function enableManualDraw(imageId) {
    const canvas = document.getElementById(`canvas-${imageId}`);
    const img = document.getElementById(`img-${imageId}`);
    const imageState = state.images.get(imageId);
    if (!canvas || !img || !imageState) return;

    // 이전 그리기 모드 리스너 제거
    if (manualDrawControllers.has(imageId)) {
        manualDrawControllers.get(imageId).abort();
    }
    const controller = new AbortController();
    manualDrawControllers.set(imageId, controller);
    const { signal } = controller;

    // 기존 bbox 오버레이 숨김 → 그리기 중 시각 충돌 방지
    const overlayContainer = document.getElementById(`bbox-overlay-${imageId}`);
    if (overlayContainer) overlayContainer.style.visibility = 'hidden';

    // canvas를 이미지와 정확히 겹치도록 위치 설정 (좌표계 통일)
    const imgRect = img.getBoundingClientRect();
    const containerRect = img.parentElement.getBoundingClientRect();
    canvas.width = img.clientWidth;
    canvas.height = img.clientHeight;
    canvas.style.left = `${imgRect.left - containerRect.left}px`;
    canvas.style.top  = `${imgRect.top  - containerRect.top}px`;
    canvas.style.zIndex = '10';
    canvas.style.cursor = 'crosshair';

    const ctx = canvas.getContext('2d');
    let isDrawing = false;
    let startX, startY;

    // canvas와 이미지가 정확히 겹치므로 canvas rect 기준으로만 계산
    const getPos = (e) => {
        const rect = canvas.getBoundingClientRect();
        return {
            x: Math.max(0, Math.min(canvas.width,  e.clientX - rect.left)),
            y: Math.max(0, Math.min(canvas.height, e.clientY - rect.top))
        };
    };

    const onMouseDown = (e) => {
        isDrawing = true;
        const pos = getPos(e);
        startX = pos.x;
        startY = pos.y;
        e.preventDefault();
    };

    // mousemove / mouseup 은 document 에 등록 → 캔버스 밖으로 나가도 추적
    const onMouseMove = (e) => {
        if (!isDrawing) return;
        const pos = getPos(e);
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.setLineDash([6, 3]);
        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth = 2;
        ctx.strokeRect(startX, startY, pos.x - startX, pos.y - startY);
        ctx.setLineDash([]);
    };

    const finishDraw = (e) => {
        if (!isDrawing) return;
        isDrawing = false;

        const pos = getPos(e);
        const x1 = Math.min(startX, pos.x);
        const y1 = Math.min(startY, pos.y);
        const x2 = Math.max(startX, pos.x);
        const y2 = Math.max(startY, pos.y);

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // 최소 크기 미달 → abort 하지 않고 그리기 모드 유지
        if ((x2 - x1) < 50 || (y2 - y1) < 50) {
            showToast('영역이 너무 작습니다. 다시 드래그하세요.', 'error');
            isDrawing = false;
            return;
        }

        // 그리기 완료 → 리스너 제거 및 canvas 위치 복원
        controller.abort();
        manualDrawControllers.delete(imageId);
        canvas.style.left = '0';
        canvas.style.top  = '0';
        canvas.style.zIndex = '';
        canvas.style.cursor = '';

        // 원본 픽셀 좌표 변환 (canvas = 이미지와 같은 크기이므로 단순 스케일)
        const scaleX = img.naturalWidth / canvas.width;
        const scaleY = img.naturalHeight / canvas.height;
        const origBbox = [
            Math.round(x1 * scaleX),
            Math.round(y1 * scaleY),
            Math.round(x2 * scaleX),
            Math.round(y2 * scaleY)
        ];

        // 오버레이 생성 (드래그/리사이즈 가능)
        if (overlayContainer) overlayContainer.style.visibility = '';
        createBboxOverlay(imageId, origBbox);
        imageState.selectedBbox = origBbox;

        imageState.status = 'detected';
        updateStatus(imageId, 'detected', '수동 영역 지정');

        const analyzeBtn = document.getElementById(`analyze-btn-${imageId}`);
        if (analyzeBtn) {
            analyzeBtn.disabled = false;
            analyzeBtn.onclick = () => analyzeVehicle(imageId);
        }

        renderStats();
    };

    canvas.addEventListener('mousedown', onMouseDown, { signal });
    document.addEventListener('mousemove', onMouseMove, { signal });
    document.addEventListener('mouseup', finishDraw, { signal });
}

function resetManualDraw(imageId) {
    const overlayContainer = document.getElementById(`bbox-overlay-${imageId}`);
    if (overlayContainer) overlayContainer.innerHTML = '';

    const imageState = state.images.get(imageId);
    if (imageState) {
        imageState.selectedBbox = null;
    }

    enableManualDraw(imageId);  // AbortController로 이전 리스너 자동 정리됨
}

function selectDetection(imageId, detectionIdx) {
    const imageState = state.images.get(imageId);
    if (!imageState || !imageState.detections[detectionIdx]) return;

    const detection = imageState.detections[detectionIdx];

    // UI 업데이트
    const detectionItems = document.querySelectorAll(`#detection-list-${imageId} .list-group-item`);
    detectionItems.forEach((item, idx) => {
        item.classList.toggle('active', idx === detectionIdx);
    });

    // 캔버스의 모든 박스 지우기
    const canvas = document.getElementById(`canvas-${imageId}`);
    if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    // 바운딩 박스 오버레이 생성
    createBboxOverlay(imageId, detection.bbox);

    imageState.selectedBbox = detection.bbox;
}

function createBboxOverlay(imageId, bbox) {
    const overlayContainer = document.getElementById(`bbox-overlay-${imageId}`);
    const img = document.getElementById(`img-${imageId}`);

    if (!img || !img.naturalWidth) return;

    // 오버레이 표시 전 캔버스 감지 박스 제거 (잔상 방지)
    const canvas = document.getElementById(`canvas-${imageId}`);
    if (canvas) canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);

    // 이미지의 실제 표시 크기와 위치 계산
    const imgRect = img.getBoundingClientRect();
    const containerRect = img.parentElement.getBoundingClientRect();

    // 컨테이너 내에서 이미지의 offset
    const imgOffsetX = imgRect.left - containerRect.left;
    const imgOffsetY = imgRect.top - containerRect.top;

    const scaleX = img.clientWidth / img.naturalWidth;
    const scaleY = img.clientHeight / img.naturalHeight;

    const [x1, y1, x2, y2] = bbox;
    const sx1 = x1 * scaleX + imgOffsetX;
    const sy1 = y1 * scaleY + imgOffsetY;
    const sx2 = x2 * scaleX + imgOffsetX;
    const sy2 = y2 * scaleY + imgOffsetY;

    overlayContainer.innerHTML = `
        <div class="bbox-overlay" id="bbox-${imageId}" style="
            left: ${sx1}px;
            top: ${sy1}px;
            width: ${sx2 - sx1}px;
            height: ${sy2 - sy1}px;
        ">
            <div class="bbox-label">드래그하여 조정 가능</div>
            <div class="bbox-handle nw"></div>
            <div class="bbox-handle ne"></div>
            <div class="bbox-handle sw"></div>
            <div class="bbox-handle se"></div>
        </div>
    `;

    // 드래그 이벤트 추가
    makeBboxDraggable(imageId);
}

function makeBboxDraggable(imageId) {
    const bboxElement = document.getElementById(`bbox-${imageId}`);
    if (!bboxElement) return;

    let isDragging = false;
    let startX, startY, startLeft, startTop;

    // 박스 이동
    bboxElement.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('bbox-handle')) return;

        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;
        startLeft = bboxElement.offsetLeft;
        startTop = bboxElement.offsetTop;
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;

        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        const newLeft = startLeft + dx;
        const newTop = startTop + dy;

        const img = document.getElementById(`img-${imageId}`);
        const imgRect = img.getBoundingClientRect();
        const containerRect = img.parentElement.getBoundingClientRect();

        const imgOffsetX = imgRect.left - containerRect.left;
        const imgOffsetY = imgRect.top - containerRect.top;

        // 이미지 영역 내로 제한
        const minLeft = imgOffsetX;
        const minTop = imgOffsetY;
        const maxLeft = imgOffsetX + img.clientWidth - bboxElement.offsetWidth;
        const maxTop = imgOffsetY + img.clientHeight - bboxElement.offsetHeight;

        bboxElement.style.left = `${Math.max(minLeft, Math.min(maxLeft, newLeft))}px`;
        bboxElement.style.top = `${Math.max(minTop, Math.min(maxTop, newTop))}px`;
    });

    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            updateBboxFromOverlay(imageId);
        }
    });

    // 리사이즈 핸들
    const handles = bboxElement.querySelectorAll('.bbox-handle');
    handles.forEach(handle => {
        handle.addEventListener('mousedown', (e) => {
            e.stopPropagation();
            handleResize(imageId, handle.classList[1], e);
        });
    });
}

function handleResize(imageId, handleType, startEvent) {
    const bboxElement = document.getElementById(`bbox-${imageId}`);
    const img = document.getElementById(`img-${imageId}`);
    const imgRect = img.getBoundingClientRect();
    const containerRect = img.parentElement.getBoundingClientRect();

    const imgOffsetX = imgRect.left - containerRect.left;
    const imgOffsetY = imgRect.top - containerRect.top;
    const imgMaxX = imgOffsetX + img.clientWidth;
    const imgMaxY = imgOffsetY + img.clientHeight;

    const startX = startEvent.clientX;
    const startY = startEvent.clientY;
    const startLeft = bboxElement.offsetLeft;
    const startTop = bboxElement.offsetTop;
    const startWidth = bboxElement.offsetWidth;
    const startHeight = bboxElement.offsetHeight;

    const onMouseMove = (e) => {
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        if (handleType === 'se') {
            const newWidth = Math.max(50, Math.min(imgMaxX - startLeft, startWidth + dx));
            const newHeight = Math.max(50, Math.min(imgMaxY - startTop, startHeight + dy));
            bboxElement.style.width = `${newWidth}px`;
            bboxElement.style.height = `${newHeight}px`;
        } else if (handleType === 'nw') {
            const newWidth = startWidth - dx;
            const newHeight = startHeight - dy;
            const newLeft = startLeft + dx;
            const newTop = startTop + dy;

            if (newWidth >= 50 && newHeight >= 50 && newLeft >= imgOffsetX && newTop >= imgOffsetY) {
                bboxElement.style.left = `${newLeft}px`;
                bboxElement.style.top = `${newTop}px`;
                bboxElement.style.width = `${newWidth}px`;
                bboxElement.style.height = `${newHeight}px`;
            }
        } else if (handleType === 'ne') {
            const newHeight = startHeight - dy;
            const newTop = startTop + dy;
            const newWidth = Math.max(50, Math.min(imgMaxX - startLeft, startWidth + dx));

            if (newHeight >= 50 && newTop >= imgOffsetY) {
                bboxElement.style.top = `${newTop}px`;
                bboxElement.style.width = `${newWidth}px`;
                bboxElement.style.height = `${newHeight}px`;
            }
        } else if (handleType === 'sw') {
            const newWidth = startWidth - dx;
            const newLeft = startLeft + dx;
            const newHeight = Math.max(50, Math.min(imgMaxY - startTop, startHeight + dy));

            if (newWidth >= 50 && newLeft >= imgOffsetX) {
                bboxElement.style.left = `${newLeft}px`;
                bboxElement.style.width = `${newWidth}px`;
                bboxElement.style.height = `${newHeight}px`;
            }
        }
    };

    const onMouseUp = () => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        updateBboxFromOverlay(imageId);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    startEvent.preventDefault();
}

function updateBboxFromOverlay(imageId) {
    const bboxElement = document.getElementById(`bbox-${imageId}`);
    const img = document.getElementById(`img-${imageId}`);

    if (!bboxElement || !img || !img.naturalWidth) return;

    // 이미지의 실제 표시 크기와 위치 계산
    const imgRect = img.getBoundingClientRect();
    const containerRect = img.parentElement.getBoundingClientRect();

    // 컨테이너 내에서 이미지의 offset
    const imgOffsetX = imgRect.left - containerRect.left;
    const imgOffsetY = imgRect.top - containerRect.top;

    const scaleX = img.naturalWidth / img.clientWidth;
    const scaleY = img.naturalHeight / img.clientHeight;

    // bbox의 좌표에서 이미지 offset을 빼서 실제 이미지 내 좌표로 변환
    const x1 = Math.round((bboxElement.offsetLeft - imgOffsetX) * scaleX);
    const y1 = Math.round((bboxElement.offsetTop - imgOffsetY) * scaleY);
    const x2 = Math.round((bboxElement.offsetLeft + bboxElement.offsetWidth - imgOffsetX) * scaleX);
    const y2 = Math.round((bboxElement.offsetTop + bboxElement.offsetHeight - imgOffsetY) * scaleY);

    const imageState = state.images.get(imageId);
    if (imageState) {
        imageState.selectedBbox = [x1, y1, x2, y2];
    }
}

//=============================================================================
// 차량 분석 (SSE 스트리밍)
//=============================================================================

// 분석 API 호출 공통 함수 (analyzeVehicle, analyzeImageSimple 공유)
async function runAnalysisStream(imageId, imageState, countStats = false) {
    const formData = new FormData();
    formData.append('bbox', JSON.stringify(imageState.selectedBbox));
    // analyzed_id 우선: DB-first 업로드 ID 또는 재분석 시 기존 레코드 ID
    const effectiveId = imageState.analyzedId || imageState.result?.id;
    if (effectiveId) {
        formData.append('analyzed_id', effectiveId);
    } else {
        formData.append('file', imageState.file);  // 하위 호환
    }

    const response = await fetch(`${API_BASE}/api/analyze-vehicle-stream`, {
        method: 'POST',
        body: formData
    });

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');

        for (let i = 0; i < lines.length - 1; i++) {
            const line = lines[i].trim();
            if (line.startsWith('data: ')) {
                try {
                    const data = JSON.parse(line.substring(6));
                    handleStreamEvent(imageId, data, countStats);
                } catch (e) {
                    console.error('Failed to parse SSE data:', line, e);
                }
            }
        }

        buffer = lines[lines.length - 1];
    }
}

// 개별 분석 버튼용
async function analyzeVehicle(imageId) {
    const imageState = state.images.get(imageId);

    if (!imageState || !imageState.selectedBbox) {
        showToast('바운딩 박스를 선택해주세요', 'error');
        return;
    }

    // 재분석 시 수정/저장 버튼 숨김 (결과 갱신 후 다시 표시됨)
    if (imageState.result?.id) {
        const editBtnR = document.getElementById(`edit-btn-${imageId}`);
        if (editBtnR) editBtnR.style.display = 'none';
        const saveBtnR = document.getElementById(`save-btn-${imageId}`);
        if (saveBtnR) saveBtnR.style.display = 'none';
    }

    updateStatus(imageId, 'analyzing', '분석 중');

    const analyzeBtn = document.getElementById(`analyze-btn-${imageId}`);
    if (analyzeBtn) {
        analyzeBtn.disabled = true;
        analyzeBtn.textContent = '분석 중...';
    }

    const progressBar = document.getElementById(`progress-${imageId}`);
    if (progressBar) {
        progressBar.style.display = 'block';
        const fill = progressBar.querySelector('.progress-bar');
        fill.style.width = '0%';
    }

    try {
        await runAnalysisStream(imageId, imageState);
    } catch (error) {
        console.error('Analysis error:', error);
        updateStatus(imageId, 'error', '분석 실패');
        imageState.status = 'analysis_error';
        renderStats();
        showToast(`분석 실패: ${error.message}`, 'error');

        if (progressBar) progressBar.style.display = 'none';
        if (analyzeBtn) {
            analyzeBtn.disabled = false;
            analyzeBtn.textContent = '재분석';
        }
    }
}

// 일괄 분석용 (버튼 조작 없이 분석만 실행)
async function analyzeImageSimple(imageId, imageState) {
    await runAnalysisStream(imageId, imageState, true);

    // 폴더 감시 모드: 분석 완료 시 자동 벡터DB 저장 (카드는 "저장 완료" 상태로 유지)
    const current = state.images.get(imageId);
    if (current?.source === 'folder' && current.status === 'completed' && current.result?.id) {
        await saveImageToVectorDB(imageId, { silent: true });
    }
}

function handleStreamEvent(imageId, data, countStats = false) {
    const imageState = state.images.get(imageId);
    if (!imageState) return;

    const progressBar = document.getElementById(`progress-${imageId}`);
    const analyzeBtn = document.getElementById(`analyze-btn-${imageId}`);

    if (data.event === 'progress') {
        // 진행률 업데이트
        if (progressBar) {
            const fill = progressBar.querySelector('.progress-bar');
            fill.style.width = `${data.progress}%`;
        }
        updateStatus(imageId, 'analyzing', data.message || '분석 중');

    } else if (data.event === 'dedup_match') {
        // 학습 데이터 중복제거 매치
        if (progressBar) {
            const fill = progressBar.querySelector('.progress-bar');
            fill.style.width = data.progress + '%';
        }
        updateStatus(imageId, 'analyzing', data.message || '학습 데이터 일치');

        // dedup 배지 표시
        const infoDiv = document.getElementById(`info-${imageId}`);
        if (infoDiv) {
            let badge = infoDiv.querySelector('.dedup-badge');
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'badge bg-info-subtle text-info-emphasis mt-1';
                const h4 = infoDiv.querySelector('h6') || infoDiv.querySelector('h4');
                if (h4) h4.after(badge);
            }
            badge.textContent = data.message || `학습 데이터 일치 (유사도: ${data.similarity})`;
        }

    } else if (data.event === 'completed') {
        imageState.result = data.result;

        const hasNull = !data.result.manufacturer || !data.result.model;

        if (hasNull) {
            // 제조사 또는 모델이 null → 분석 실패로 카운트
            imageState.status = 'analysis_error';
            if (countStats) incrementStat(imageState.source, 'analysisError');
            displayResult(imageId, data.result);
            updateStatus(imageId, 'error', 'null 인식 실패');
            renderStats();

            if (progressBar) progressBar.style.display = 'none';
            if (analyzeBtn) {
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = '재분석';
            }

            // 수정은 가능하도록 편집 버튼만 표시, 저장 버튼은 숨김
            const editBtnN = document.getElementById(`edit-btn-${imageId}`);
            if (editBtnN) editBtnN.style.display = '';

            showToast(`인식 실패: 제조사 또는 모델이 null입니다. 수정 후 저장해주세요.`, 'error');
        } else {
            // 정상 완료 → 재시도 큐(이미지 분석 페이지)에서 자동 제거
            imageState.status = 'completed';
            if (countStats) incrementStat(imageState.source, 'analyzed');
            displayResult(imageId, data.result);
            updateStatus(imageId, 'completed', '분석 완료 — 관리자 페이지로 이동됩니다');
            renderStats();

            if (progressBar) progressBar.style.display = 'none';
            if (analyzeBtn) analyzeBtn.disabled = true;

            showToast(`분석 완료: ${data.result.manufacturer} ${data.result.model} — 관리자에서 확인하세요`);

            // 2초 후 카드 자동 제거 (성공 결과 확인 시간 허용)
            setTimeout(() => {
                const card = document.getElementById(`image-${imageId}`);
                if (card) {
                    card.style.transition = 'opacity 0.5s';
                    card.style.opacity = '0';
                    setTimeout(() => {
                        card.remove();
                        if (state.hydrateState[imageState.source].totalCount > 0)
                            state.hydrateState[imageState.source].totalCount--;
                        state.images.delete(imageId);
                        renderStats();
                    }, 500);
                }
            }, 2000);
        }

    } else if (data.event === 'error') {
        // 에러 처리
        imageState.status = 'analysis_error';
        if (countStats) incrementStat(imageState.source, 'analysisError');
        updateStatus(imageId, 'error', '분석 실패');
        renderStats();

        if (progressBar) progressBar.style.display = 'none';
        if (analyzeBtn) {
            analyzeBtn.disabled = false;
            analyzeBtn.textContent = '재분석';
        }

        showToast(`분석 실패: ${data.message}`, 'error');
    }
}

function displayResult(imageId, result) {
    const resultContainer = document.getElementById(`result-${imageId}`);
    if (!resultContainer) return;

    resultContainer.style.display = 'block';
    resultContainer.innerHTML = `
        <div class="d-flex justify-content-between py-1 small">
            <span class="fw-semibold text-muted">제조사:</span>
            <span class="fw-medium">${result.manufacturer || 'N/A'}</span>
        </div>
        <div class="d-flex justify-content-between py-1 small">
            <span class="fw-semibold text-muted">모델:</span>
            <span class="fw-medium">${result.model || 'N/A'}</span>
        </div>
        <div class="d-flex justify-content-between py-1 small">
            <span class="fw-semibold text-muted">식별 신뢰도:</span>
            <span class="fw-medium">${result.confidence_score ? result.confidence_score.toFixed(1) + '%' : 'N/A'}</span>
        </div>
    `;
}

//=============================================================================
// 유틸리티
//=============================================================================

function updateStatus(imageId, statusType, text) {
    const statusBadge = document.getElementById(`status-${imageId}`);
    if (!statusBadge) return;

    const typeMap = { detecting: 'warning', detected: 'info', analyzing: 'primary', completed: 'success', verified: 'success', error: 'danger', 'manually-edited': 'info' };
    statusBadge.className = `badge rounded-pill bg-${typeMap[statusType] || 'secondary'}`;
    statusBadge.textContent = text;
}

function incrementStat(source, field, delta = 1) {
    const stats = source === 'folder' ? state.folderStats : state.fileStats;
    stats[field] = Math.max(0, (stats[field] || 0) + delta);
    const key = source === 'folder' ? 'reeve_folder_stats' : 'reeve_file_stats';
    localStorage.setItem(`${key}_${CLIENT_UUID}`, JSON.stringify(stats));
    renderStats();
}

function renderStats() {
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

    // ── 파일 탭 ──
    const fs = state.fileStats;
    set('fileStatTotal', fs.uploaded);
    set('fileStatDetected', fs.detected);
    set('fileStatDetectionFailed', fs.detectionFailed || 0);

    set('fileStatAnalyzed', fs.analyzed);
    set('fileStatAnalysisError', fs.analysisError + (fs.manuallyEdited || 0));

    // 인식률
    const fileAttempted = fs.analyzed + fs.analysisError + (fs.manuallyEdited || 0);
    const fileRateEl = document.getElementById('fileStatRecognitionRate');
    if (fileRateEl) {
        if (fileAttempted > 0) {
            const pct = Math.round(fs.analyzed / fileAttempted * 100);
            fileRateEl.textContent = `${pct}%`;
            fileRateEl.style.color = pct >= 80 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444';
        } else {
            fileRateEl.textContent = '-';
            fileRateEl.style.color = '#aab';
        }
    }

    // ── 폴더 탭 ──
    const fls = state.folderStats;
    set('folderStatTotal', fls.uploaded);
    set('folderStatDetected', fls.detected);
    set('folderStatDetectionFailed', fls.detectionFailed || 0);

    set('folderStatAnalyzed', fls.analyzed);
    set('folderStatAnalysisError', fls.analysisError);

    const folderAttempted = fls.analyzed + fls.analysisError;
    const folderRateEl = document.getElementById('folderStatRecognitionRate');
    if (folderRateEl) {
        if (folderAttempted > 0) {
            const pct = Math.round(fls.analyzed / folderAttempted * 100);
            folderRateEl.textContent = `${pct}%`;
            folderRateEl.style.color = pct >= 80 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444';
        } else {
            folderRateEl.textContent = '-';
            folderRateEl.style.color = '#aab';
        }
    }

}

async function removeImage(imageId) {
    if (!confirm('이 이미지를 삭제하시겠습니까?')) return;

    // 수동 드래그 모드 중이면 종료
    if (manualDrawControllers.has(imageId)) {
        manualDrawControllers.get(imageId).abort();
        manualDrawControllers.delete(imageId);
    }

    // DB 레코드 삭제 (업로드 직후 또는 분석 완료된 경우)
    const imageState = state.images.get(imageId);
    const deleteId = imageState?.analyzedId || imageState?.result?.id;
    if (deleteId) {
        try {
            await fetch(`${API_BASE}/admin/review/${deleteId}`, { method: 'DELETE' });
        } catch (e) {
            console.warn('DB 삭제 실패:', e);
        }
    }

    const card = document.getElementById(`image-${imageId}`);
    if (card) card.remove();

    const src = imageState?.source || 'file';
    if (state.hydrateState[src].totalCount > 0) state.hydrateState[src].totalCount--;
    state.images.delete(imageId);
    renderStats();
    // 현재 페이지 리로드 (빈 자리 채우기)
    loadRecordsPage(src);
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = 'reeve-toast';
    toast.textContent = message;

    if (type === 'error') {
        toast.style.background = '#ef4444';
    } else if (type === 'success') {
        toast.style.background = '#10b981';
    }

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

//=============================================================================
// 일괄 분석
//=============================================================================

const batchAnalyzeBtn = document.getElementById('batchAnalyzeBtn');
const batchStopBtn = document.getElementById('batchStopBtn');
let batchAborted = false;

batchAnalyzeBtn.addEventListener('click', startBatchAnalysis);
batchStopBtn.addEventListener('click', stopBatchAnalysis);

function stopBatchAnalysis() {
    batchAborted = true;
    batchStopBtn.disabled = true;
    batchStopBtn.textContent = '⏹️ 중지 중...';
}

// 이미지 상태 변경 시 일괄 분석 버튼 표시/숨김
// 차량이 감지된(status==='detected') 이미지만 대상

async function startBatchAnalysis() {
    // 파일 탭 이미지만 대상 (폴더 감시는 자동 분석)
    // detected(감지 완료) + analysis_error(재분석 대상) 카드를 배치 분석
    const unanalyzedImages = Array.from(state.images.entries())
        .filter(([id, img]) => img.source !== 'folder' &&
            (img.status === 'detected' || img.status === 'analysis_error') &&
            img.selectedBbox);

    if (unanalyzedImages.length === 0) {
        showToast('분석할 이미지가 없습니다. (차량이 감지된 이미지가 필요합니다)', 'error');
        return;
    }

    // 사용자 확인
    const estimatedMinutes = Math.ceil(unanalyzedImages.length / 15);
    if (!confirm(`${unanalyzedImages.length}개의 이미지를 일괄 분석하시겠습니까?\n\n⏱️ 예상 소요 시간: 약 ${estimatedMinutes}분\n💡 API 사용량 제한을 고려하여 4초 간격으로 순차 처리됩니다.`)) {
        return;
    }

    // 중지 플래그 초기화
    batchAborted = false;

    // UI 초기화
    const progressContainer = document.getElementById('batchProgressContainer');
    const progressBar = document.getElementById('batchProgressBar');
    const progressText = document.getElementById('batchProgressText');

    progressContainer.style.display = 'block';
    batchAnalyzeBtn.disabled = true;
    batchStopBtn.style.display = 'inline-block';
    batchStopBtn.disabled = false;
    batchStopBtn.textContent = '⏹️ 전체 일괄 분석 중지';

    // API 사용량 제한 고려: 15 images/minute = 4초 간격 (Too Many Requests 방지)
    const DELAY_MS = 4000;

    let completed = 0;
    let succeeded = 0;
    let failed = 0;

    for (let i = 0; i < unanalyzedImages.length; i++) {
        // 중지 확인
        if (batchAborted) {
            // 현재 분석 중인 이미지 상태 복원 (아직 시작 안 한 것들)
            for (let j = i; j < unanalyzedImages.length; j++) {
                const [remainId, remainState] = unanalyzedImages[j];
                if (remainState.status === 'analyzing') {
                    updateStatus(remainId, 'detected', '감지 완료');
                    remainState.status = 'detected';
                }
            }
            break;
        }

        const [imageId, imageState] = unanalyzedImages[i];

        try {
            // 선택된 바운딩 박스가 있는지 확인
            if (!imageState.selectedBbox) {
                console.warn(`Image ${imageId}: No bbox selected, skipping`);
                imageState.status = 'analysis_error';
                updateStatus(imageId, 'error', '바운딩 박스 없음');
                failed++;
                completed++;
                renderStats();
                continue;
            }

            // 분석 시작 상태로 변경
            updateStatus(imageId, 'analyzing', '분석 중...');
            imageState.status = 'analyzing';
            renderStats();

            // 분석 실행 (SSE 스트리밍)
            await analyzeImageSimple(imageId, imageState);
            succeeded++;

        } catch (error) {
            console.error(`Failed to analyze image ${imageId}:`, error);
            updateStatus(imageId, 'error', '분석 실패');
            imageState.status = 'analysis_error';
            failed++;
        }

        completed++;

        // 진행률 업데이트
        const progress = Math.round((completed / unanalyzedImages.length) * 100);
        progressBar.style.width = `${progress}%`;
        progressBar.textContent = `${progress}%`;
        progressText.textContent = `진행: ${completed}/${unanalyzedImages.length} (✅ OpenAI 성공: ${succeeded}, ❌ 실패: ${failed})`;

        renderStats();

        // 마지막 이미지가 아니면 대기
        if (i < unanalyzedImages.length - 1) {
            await new Promise(resolve => setTimeout(resolve, DELAY_MS));
        }
    }

    // 중지 버튼 숨기기
    batchStopBtn.style.display = 'none';

    // 완료/중지 메시지
    const remaining = unanalyzedImages.length - completed;
    if (batchAborted) {
        progressText.textContent = `⏹️ 중지됨! ${completed}/${unanalyzedImages.length}개 처리 (✅ 성공: ${succeeded}, ❌ 실패: ${failed}, ⏭️ 미처리: ${remaining})`;
        showToast(`일괄 분석 중지: ${succeeded}개 성공, ${remaining}개 미처리`, 'info');
        batchAnalyzeBtn.disabled = false;
    } else {
        // 완료 시: 새 이미지 업로드 UX 표시
        progressText.innerHTML = `✨ 완료! 총 ${unanalyzedImages.length}개 중 ${succeeded}개 성공, ${failed}개 실패
            <br><br>
            <button onclick="window.location.reload()" style="
                background: #667eea; color: white; border: none; padding: 10px 20px;
                border-radius: 6px; font-size: 14px; cursor: pointer; font-weight: 600;
            ">📤 새 이미지 업로드하기</button>`;
        showToast(`일괄 분석 완료: 성공 ${succeeded}개, 실패 ${failed}개`, succeeded > 0 ? 'success' : 'error');
        batchAnalyzeBtn.disabled = false;
    }
}


//=============================================================================
// 분석결과 수정 모달
//=============================================================================

// 제조사 목록 (모달용)
const editModalState = { manufacturers: [] };

// 제조사 목록 로드
async function loadManufacturersForModal() {
    try {
        const response = await fetch(`${API_BASE}/admin/manufacturers?limit=1000`);
        if (!response.ok) return;
        editModalState.manufacturers = await response.json();
    } catch (e) {
        console.warn('제조사 목록 로드 실패:', e);
    }
}

// 모달 열기
async function openAnalysisEditModal(imageId) {
    const imageState = state.images.get(imageId);
    if (!imageState?.result) return;

    const result = imageState.result;
    const modal = document.getElementById('imageDetailModal');

    document.getElementById('editImageId').value = imageId;
    document.getElementById('editAnalyzedId').value = result.id || '';
    document.getElementById('imageDetailTitle').textContent = `분석결과 수정 #${result.id || ''}`;
    document.getElementById('currentAnalysis').textContent = `현재: ${result.manufacturer || 'N/A'} ${result.model || 'N/A'}`;

    // 이미지 표시 (파일 객체에서 URL 생성)
    const detailImg = document.getElementById('detailImage');
    const imgEl = document.getElementById(`img-${imageId}`);
    if (imgEl && imgEl.src) {
        detailImg.src = imgEl.src;
    }

    // 제조사 목록이 없으면 로드
    if (editModalState.manufacturers.length === 0) {
        await loadManufacturersForModal();
    }

    // 제조사 셀렉트 채우기
    const mfSelect = document.getElementById('editManufacturer');
    mfSelect.innerHTML = '<option value="">제조사 선택</option>' +
        editModalState.manufacturers.map(mf =>
            `<option value="${mf.id}" data-code="${mf.code}">${mf.korean_name} (${mf.code})</option>`
        ).join('');

    if (result.matched_manufacturer_id) mfSelect.value = result.matched_manufacturer_id;

    // 모델 셀렉트 채우기
    await loadModelsForEditModal(result.matched_manufacturer_id, result.matched_model_id);

    // 인라인 추가 영역 초기화
    closeInlineAddManufacturer();
    closeInlineAddModel();

    bootstrap.Modal.getOrCreateInstance(modal).show();
}

// 탭 전환 후 숨겨진 상태에서 렌더된 canvas/bbox 재초기화
function refreshTabBboxes(source) {
    state.images.forEach((imageState, imageId) => {
        if (imageState.source !== source) return;
        const img    = document.getElementById(`img-${imageId}`);
        const canvas = document.getElementById(`canvas-${imageId}`);
        if (!img || !canvas || img.clientWidth === 0) return;

        canvas.width  = img.clientWidth;
        canvas.height = img.clientHeight;

        if (imageState.detections?.length > 0) {
            drawAllBboxes(imageId, imageState.detections);
        }
        if (imageState.selectedBbox) {
            createBboxOverlay(imageId, imageState.selectedBbox);
        }
    });
}

// 제조사 변경 시 모델 목록 업데이트
document.addEventListener('DOMContentLoaded', async () => {
    // 모달 닫기 버튼 (Bootstrap Modal API)
    const imageDetailModal = document.getElementById('imageDetailModal');
    document.getElementById('imageDetailCloseBtn').addEventListener('click', () => {
        bootstrap.Modal.getInstance(imageDetailModal)?.hide();
    });
    document.getElementById('imageDetailCloseBtn2').addEventListener('click', () => {
        bootstrap.Modal.getInstance(imageDetailModal)?.hide();
    });

    // 제조사 변경 시 모델 업데이트
    const mfSelect = document.getElementById('editManufacturer');
    if (mfSelect) {
        mfSelect.addEventListener('change', () => {
            const mfId = mfSelect.value ? parseInt(mfSelect.value) : null;
            loadModelsForEditModal(mfId, null);
        });
    }

    // 제조사 미리 로드
    loadManufacturersForModal();

    // 탭 복원
    const savedTab = localStorage.getItem('reeve_active_tab') || 'file';
    if (savedTab === 'folder') {
        bootstrap.Tab.getOrCreateInstance(document.getElementById('snbTabFolder')).show();
    }

    // SNB 탭 전환 이벤트: localStorage 저장 + 폴더감시 중지 + bbox 재렌더
    document.getElementById('snbTabFile')?.addEventListener('shown.bs.tab', () => {
        localStorage.setItem('reeve_active_tab', 'file');
        if (folderWatch.intervalId) stopFolderWatch();
        refreshTabBboxes('file');
    });
    document.getElementById('snbTabFolder')?.addEventListener('shown.bs.tab', () => {
        localStorage.setItem('reeve_active_tab', 'folder');
        refreshTabBboxes('folder');
    });

    // Stats 복원 (이미 state 초기화에서 localStorage로부터 로드됨)
    renderStats();

    // DB에서 미완료 레코드 복원 (탭별 병렬) + SSE 피드
    await Promise.all([
        loadRecordsPage('file'),
        loadRecordsPage('folder')
    ]);
    startAnalyzeFeed();
});

async function loadModelsForEditModal(manufacturerId, selectedModelId) {
    const modelSelect = document.getElementById('editModel');
    if (!manufacturerId) {
        modelSelect.innerHTML = '<option value="">제조사를 먼저 선택하세요</option>';
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/admin/vehicle-models?manufacturer_id=${manufacturerId}&limit=1000`);
        if (!response.ok) throw new Error('모델 로드 실패');
        const models = await response.json();
        modelSelect.innerHTML = '<option value="">모델 선택</option>' +
            models.map(m => `<option value="${m.id}">${m.korean_name} (${m.code})</option>`).join('');
        if (selectedModelId) modelSelect.value = selectedModelId;
    } catch (e) {
        modelSelect.innerHTML = '<option value="">모델 로드 실패</option>';
    }
}

// 수정 저장
async function saveEditedAnalysis() {
    const imageId = document.getElementById('editImageId').value;
    const analyzedId = document.getElementById('editAnalyzedId').value;
    const mfSelect = document.getElementById('editManufacturer');
    const modelSelect = document.getElementById('editModel');

    if (!mfSelect.value || !modelSelect.value) {
        alert('제조사와 모델을 모두 선택해주세요.');
        return;
    }

    const newManufacturer = mfSelect.options[mfSelect.selectedIndex].textContent.split(' (')[0];
    const newModel = modelSelect.options[modelSelect.selectedIndex].textContent.split(' (')[0];
    const newMfId = parseInt(mfSelect.value);
    const newModelId = parseInt(modelSelect.value);

    try {
        const response = await fetch(`${API_BASE}/admin/review/${analyzedId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                matched_manufacturer_id: newMfId,
                matched_model_id: newModelId,
                manufacturer: newManufacturer,
                model: newModel
            })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || '수정 실패');
        }

        // 카드의 result 상태 업데이트
        const imageState = state.images.get(imageId);
        if (imageState?.result) {
            imageState.result.manufacturer = newManufacturer;
            imageState.result.model = newModel;
            imageState.result.matched_manufacturer_id = newMfId;
            imageState.result.matched_model_id = newModelId;
            // null 인식 실패 상태였다면 수동 수정으로 전환 후 저장 버튼 표시
            // (통계상 자동 인식 완료로는 카운트되지 않음)
            if (imageState.status === 'analysis_error') {
                imageState.status = 'manually_edited';
                updateStatus(imageId, 'manually-edited', '수동 수정');
                const saveBtn = document.getElementById(`save-btn-${imageId}`);
                if (saveBtn) saveBtn.style.display = '';
                renderStats();
            }
            displayResult(imageId, imageState.result);
        }

        bootstrap.Modal.getInstance(document.getElementById('imageDetailModal'))?.hide();
        showToast(`수정 완료: ${newManufacturer} ${newModel}`, 'success');
    } catch (e) {
        alert('오류: ' + e.message);
    }
}

// 인라인 제조사 추가
function openInlineAddManufacturer() {
    document.getElementById('inlineAddManufacturer').style.display = 'block';
}
function closeInlineAddManufacturer() {
    document.getElementById('inlineAddManufacturer').style.display = 'none';
    document.getElementById('inlineMfCode').value = '';
    document.getElementById('inlineMfKorean').value = '';
    document.getElementById('inlineMfEnglish').value = '';
    document.getElementById('inlineMfDomestic').checked = false;
}
async function saveInlineManufacturer() {
    const code = document.getElementById('inlineMfCode').value.trim();
    const korean = document.getElementById('inlineMfKorean').value.trim();
    const english = document.getElementById('inlineMfEnglish').value.trim();
    const isDomestic = document.getElementById('inlineMfDomestic').checked;

    if (!code || !korean || !english) {
        alert('코드, 한글명, 영문명을 모두 입력해주세요.');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/admin/manufacturers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, english_name: english, korean_name: korean, is_domestic: isDomestic })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || '추가 실패');
        }
        const newMf = await response.json();

        editModalState.manufacturers.push(newMf);

        const mfSelect = document.getElementById('editManufacturer');
        mfSelect.innerHTML = '<option value="">제조사 선택</option>' +
            editModalState.manufacturers.map(mf =>
                `<option value="${mf.id}" data-code="${mf.code}">${mf.korean_name} (${mf.code})</option>`
            ).join('');
        mfSelect.value = newMf.id;
        await loadModelsForEditModal(newMf.id, null);

        closeInlineAddManufacturer();
        showToast(`제조사 "${korean}" 추가됨`, 'success');
    } catch (e) {
        alert('오류: ' + e.message);
    }
}

// 인라인 모델 추가
function openInlineAddModel() {
    const mfId = document.getElementById('editManufacturer').value;
    if (!mfId) {
        alert('제조사를 먼저 선택해주세요.');
        return;
    }
    document.getElementById('inlineAddModel').style.display = 'block';
}
function closeInlineAddModel() {
    document.getElementById('inlineAddModel').style.display = 'none';
    document.getElementById('inlineModelCode').value = '';
    document.getElementById('inlineModelKorean').value = '';
    document.getElementById('inlineModelEnglish').value = '';
}
async function saveInlineModel() {
    const mfSelect = document.getElementById('editManufacturer');
    const mfId = parseInt(mfSelect.value);
    const mfCode = mfSelect.options[mfSelect.selectedIndex]?.dataset?.code || '';

    const code = document.getElementById('inlineModelCode').value.trim();
    const korean = document.getElementById('inlineModelKorean').value.trim();
    const english = document.getElementById('inlineModelEnglish').value.trim();

    if (!code || !korean || !english) {
        alert('코드, 한글명, 영문명을 모두 입력해주세요.');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/admin/vehicle-models`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, manufacturer_id: mfId, manufacturer_code: mfCode, english_name: english, korean_name: korean })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || '추가 실패');
        }
        const newModel = await response.json();

        await loadModelsForEditModal(mfId, newModel.id);
        closeInlineAddModel();
        showToast(`모델 "${korean}" 추가됨`, 'success');
    } catch (e) {
        alert('오류: ' + e.message);
    }
}

// 벡터DB 저장
async function saveImageToVectorDB(imageId, { silent = false } = {}) {
    const imageState = state.images.get(imageId);
    if (!imageState?.result?.id) {
        if (!silent) showToast('저장할 분석 결과가 없습니다.', 'error');
        return false;
    }

    if (!silent && !confirm('이 분석 결과를 벡터DB에 저장하시겠습니까?')) return false;

    const saveBtn = document.getElementById(`save-btn-${imageId}`);
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = '저장 중...';
    }

    try {
        const response = await fetch(`${API_BASE}/admin/review/${imageState.result.id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ approved: true })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || '저장 실패');
        }

        showToast('벡터DB에 저장되었습니다.', 'success');

        // 저장 완료 → 재시도 큐에서 자동 제거
        imageState.status = 'verified';
        const card = document.getElementById(`image-${imageId}`);
        if (card) {
            card.style.transition = 'opacity 0.5s';
            card.style.opacity = '0';
            setTimeout(() => {
                card.remove();
                if (state.hydrateState[imageState.source].totalCount > 0)
                    state.hydrateState[imageState.source].totalCount--;
                state.images.delete(imageId);
                renderStats();
            }, 500);
        } else {
            renderStats();
        }
    } catch (e) {
        showToast('저장 실패: ' + e.message, 'error');
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = '저장';
        }
    }
}

//=============================================================================
// 벡터DB 일괄 저장 / 일괄 삭제
//=============================================================================

async function startVectorBatchSave() {
    // 현재 카드 중 분석 완료 + 아직 저장 안 된 것만 대상
    const targets = Array.from(state.images.entries()).filter(([, img]) =>
        img.source !== 'folder' && (img.status === 'completed' || img.status === 'manually_edited') && img.result?.id
    );

    if (targets.length === 0) {
        showToast('저장할 분석 완료 이미지가 없습니다.', 'error');
        return;
    }

    if (!confirm(`분석 완료된 ${targets.length}개 이미지를 벡터DB에 저장하시겠습니까?\n(이미 저장된 항목은 제외됩니다)`)) return;

    const progressContainer = document.getElementById('vectorSaveProgressContainer');
    const progressBar = document.getElementById('vectorSaveProgressBar');
    const progressText = document.getElementById('vectorSaveProgressText');
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    progressBar.textContent = '0%';

    let succeeded = 0;
    let failed = 0;

    for (let i = 0; i < targets.length; i++) {
        const [imageId, imageState] = targets[i];
        progressText.textContent = `진행: ${i + 1}/${targets.length} (✅ 성공: ${succeeded}, ❌ 실패: ${failed})`;

        try {
            const response = await fetch(`${API_BASE}/admin/review/${imageState.result.id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ approved: true })
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || '저장 실패');
            }

            succeeded++;

            // 저장 완료된 카드 제거 (페이드 아웃)
            const card = document.getElementById(`image-${imageId}`);
            if (card) {
                card.style.transition = 'opacity 0.3s';
                card.style.opacity = '0';
                setTimeout(() => {
                    card.remove();
    
                    state.images.delete(imageId);
                    renderStats(); // 전체 이미지 수 등 재계산
                }, 300);
            } else {

                state.images.delete(imageId);
                renderStats();
            }
        } catch (e) {
            console.error(`Save failed for ${imageId}:`, e);
            failed++;
        }

        const pct = Math.round(((i + 1) / targets.length) * 100);
        progressBar.style.width = `${pct}%`;
        progressBar.textContent = `${pct}%`;
    }

    progressText.textContent = `✨ 완료! 총 ${targets.length}개 중 ${succeeded}개 저장 완료, ${failed}개 실패. 페이지를 새로고침합니다...`;
    showToast(`벡터DB 저장 완료: ${succeeded}개`, 'success');

    setTimeout(() => {
        window.location.reload();
    }, 1500);
}

//=============================================================================
// DB-First 복원 및 실시간 피드
//=============================================================================

async function loadRecordsPage(source = 'file') {
    const h = state.hydrateState[source];
    if (h.loading) return;
    h.loading = true;

    try {
        const skip = h.page * h.pageSize;
        const resp = await fetch(`/api/pending-records?skip=${skip}&limit=${h.pageSize}&source=${source}&client_uuid=${CLIENT_UUID}&failure_only=true`);
        if (!resp.ok) return;
        const { items, total } = await resp.json();
        h.totalCount = total;

        // 현재 페이지가 범위를 벗어나면 마지막 유효 페이지로 보정 후 재로드
        if (items.length === 0 && total > 0 && h.page > 0) {
            h.page = Math.max(0, Math.ceil(total / h.pageSize) - 1);
            clearDbCards(source);
            renderPagination(source);
            setTimeout(() => loadRecordsPage(source), 0);
            return;
        }

        // 이전 DB 로드 카드 제거 후 새 페이지 렌더
        clearDbCards(source);
        for (const record of items) {
            createImageCardFromRecord(record);
        }
        renderPagination(source);
    } catch (e) {
        console.warn('레코드 조회 실패:', e);
    } finally {
        h.loading = false;
    }
}

function clearDbCards(source) {
    const grid = source === 'folder' ? imageGridFolder : imageGridFile;
    grid.querySelectorAll('[data-db-record]').forEach(el => {
        const imageId = el.id.replace('image-', '');
        state.images.delete(imageId);
        el.remove();
    });
}

function _getPaginatedTotal(source) {
    // 라이브 업로드 카드(현재 세션)는 항상 표시되므로 페이지네이션 대상에서 제외
    const liveCount = Array.from(state.images.values())
        .filter(s => s.source === source && s.file !== null && s.analyzedId != null)
        .length;
    return Math.max(0, state.hydrateState[source].totalCount - liveCount);
}

function goToPage(source, page) {
    const totalPages = Math.ceil(_getPaginatedTotal(source) / state.hydrateState[source].pageSize);
    if (page < 0 || page >= totalPages) return;
    state.hydrateState[source].page = page;
    loadRecordsPage(source);
}

function renderPagination(source) {
    const h = state.hydrateState[source];
    const navEl = document.getElementById(source === 'folder' ? 'paginationFolder' : 'paginationFile');
    if (!navEl) return;

    const effectiveTotal = _getPaginatedTotal(source);
    const totalPages = Math.ceil(effectiveTotal / h.pageSize);
    if (totalPages <= 1) { navEl.innerHTML = ''; return; }

    const cur = h.page;
    // 최대 5페이지씩 슬라이딩 윈도우
    const half = 2;
    const start = Math.max(0, Math.min(cur - half, totalPages - 5));
    const end   = Math.min(totalPages - 1, start + 4);

    let items = '';
    if (start > 0) items += `<li class="page-item"><button class="page-link" onclick="goToPage('${source}',0)">1</button></li><li class="page-item disabled"><span class="page-link">…</span></li>`;
    for (let i = start; i <= end; i++) {
        items += `<li class="page-item${i === cur ? ' active' : ''}"><button class="page-link" onclick="goToPage('${source}',${i})">${i + 1}</button></li>`;
    }
    if (end < totalPages - 1) items += `<li class="page-item disabled"><span class="page-link">…</span></li><li class="page-item"><button class="page-link" onclick="goToPage('${source}',${totalPages - 1})">${totalPages}</button></li>`;

    navEl.innerHTML = `
        <ul class="pagination justify-content-center flex-wrap">
            <li class="page-item${cur === 0 ? ' disabled' : ''}">
                <button class="page-link" onclick="goToPage('${source}',${cur - 1})"><i class="bi bi-chevron-left"></i></button>
            </li>
            ${items}
            <li class="page-item${cur >= totalPages - 1 ? ' disabled' : ''}">
                <button class="page-link" onclick="goToPage('${source}',${cur + 1})"><i class="bi bi-chevron-right"></i></button>
            </li>
        </ul>
        <p class="text-center text-muted small">${effectiveTotal}개 중 ${source === 'folder' ? '폴더' : '파일'} ${cur + 1}/${totalPages} 페이지</p>`;
}

function createImageCardFromRecord(record) {
    const imageId = `db_${record.id}`;

    // 중복 방지 (db_ 키 또는 같은 analyzedId를 가진 라이브 카드)
    if (state.images.has(imageId)) return;
    const alreadyLive = Array.from(state.images.values()).some(s => s.analyzedId === record.id);
    if (alreadyLive) return;

    // status 결정
    let status, statusType, statusText;
    if (record.processing_stage === 'verified') {
        status = 'verified';
        statusType = 'verified';
        statusText = '저장 완료';
    } else if (record.processing_stage === 'analysis_complete') {
        if (record.manufacturer && record.model) {
            status = 'completed';
            statusType = 'completed';
            statusText = '분석 완료';
        } else {
            status = 'analysis_error';
            statusType = 'error';
            statusText = 'null 인식 실패';
        }
    } else if (record.processing_stage === 'yolo_detected') {
        if (record.yolo_detections && record.yolo_detections.length > 0) {
            status = 'detected';
            statusType = 'detected';
            statusText = `차량 ${record.yolo_detections.length}대 감지`;
        } else {
            // 감지 결과 없음 → no_vehicle로 복원 (일괄 삭제 필터 정합성)
            status = 'no_vehicle';
            statusType = 'error';
            statusText = '차량 미감지';
        }
    } else if (record.processing_stage === 'uploaded') {
        status = 'uploading';
        statusType = 'warning';
        statusText = '업로드 완료';
    } else {
        return;
    }

    // 이미지 분석 페이지: 실패 카드(분석실패/탐지실패)만 표시
    if (status !== 'analysis_error' && status !== 'no_vehicle') {
        return;
    }

    const result = (status === 'completed' || status === 'verified' || status === 'analysis_error') ? {
        id: record.id,
        manufacturer: record.manufacturer,
        model: record.model,
        year: record.year,
        confidence_score: record.confidence_score,
        matched_manufacturer_id: record.matched_manufacturer_id,
        matched_model_id: record.matched_model_id
    } : null;

    const recordSource = record.source || 'file';
    state.images.set(imageId, {
        file: null,
        analyzedId: record.id,
        originalImagePath: record.original_image_path,
        source: recordSource,
        detections: record.yolo_detections || [],
        selectedBbox: record.selected_bbox || null,
        status,
        result
    });

    renderStats();

    const displayName = record.original_image_path
        ? record.original_image_path.split('/').pop()
        : `#${record.id}`;

    const card = document.createElement('div');
    card.className = 'col';
    card.id = `image-${imageId}`;
    card.dataset.dbRecord = 'true';

    const analyzeDisabled = status === 'detected' ? '' : 'disabled';
    const editDisplay = (status === 'completed' || status === 'analysis_error') ? '' : 'none';
    const saveDisplay = status === 'completed' ? '' : 'none';  // verified는 이미 저장됨 → 숨김
    const analyzeLabel = status === 'detected' ? '분석하기' : '재분석';
    const badgeTypeMap = { detecting: 'warning', detected: 'info', analyzing: 'primary', completed: 'success', verified: 'success', error: 'danger', 'manually-edited': 'info' };
    const badgeClass = badgeTypeMap[statusType] || 'secondary';

    card.innerHTML = `
        <div class="card shadow-sm overflow-hidden">
        <div class="image-container">
            <img id="img-${imageId}" alt="${displayName}" style="display:none;">
            <canvas id="canvas-${imageId}" class="image-canvas" style="display:none;"></canvas>
            <div id="bbox-overlay-${imageId}"></div>
        </div>
        <div class="card-body">
            <h6 class="d-flex align-items-center gap-2">
                ${displayName}
                <span class="badge rounded-pill bg-${badgeClass}" id="status-${imageId}">${statusText}</span>
            </h6>
            <div id="detection-list-${imageId}" class="list-group list-group-flush my-2"></div>
            <div id="result-${imageId}" class="card bg-body-secondary p-3 mt-2" style="display: none;"></div>
            <div class="d-flex gap-2 mt-3 flex-wrap">
                <button class="btn btn-sm btn-primary" id="analyze-btn-${imageId}" ${analyzeDisabled} onclick="analyzeVehicle('${imageId}')">
                    ${analyzeLabel}
                </button>
                <button class="btn btn-sm btn-success" id="edit-btn-${imageId}" style="display:${editDisplay};" onclick="openAnalysisEditModal('${imageId}')">
                    분석결과 수정
                </button>
                <button class="btn btn-sm btn-primary" id="save-btn-${imageId}" style="display:${saveDisplay};" onclick="saveImageToVectorDB('${imageId}')">
                    저장
                </button>
                <button class="btn btn-sm btn-danger" onclick="removeImage('${imageId}')">
                    삭제
                </button>
            </div>
            <div class="progress mt-3" style="display: none; height: 4px;" id="progress-${imageId}">
                <div class="progress-bar" role="progressbar" style="width: 0%; background: linear-gradient(90deg, #667eea, #764ba2);"></div>
            </div>
        </div>
        </div>
    `;

    const targetGrid = recordSource === 'folder' ? imageGridFolder : imageGridFile;
    targetGrid.insertBefore(card, targetGrid.firstChild);

    const img = document.getElementById(`img-${imageId}`);
    const canvas = document.getElementById(`canvas-${imageId}`);

    img.onload = () => {
        img.style.display = 'block';
        canvas.style.display = 'block';
        canvas.width = img.clientWidth;
        canvas.height = img.clientHeight;

        const imageState = state.images.get(imageId);

        // 감지 결과 표시
        if (imageState.detections && imageState.detections.length > 0) {
            displayDetections(imageId, imageState.detections);
        } else if (status === 'detected' || status === 'no_vehicle') {
            enableManualDraw(imageId);
        }

        // bbox 복원
        if (imageState.selectedBbox) {
            createBboxOverlay(imageId, imageState.selectedBbox);
        }

        // 분석 결과 표시
        if (result) {
            displayResult(imageId, result);
        }

        // 탭 전환 시 canvas 재초기화 (숨김 상태에서 로드되면 clientWidth=0)
        const resizeObserver = new ResizeObserver(() => {
            const cur = state.images.get(imageId);
            if (!cur) { resizeObserver.disconnect(); return; }
            if (img.clientWidth > 0) {
                canvas.width = img.clientWidth;
                canvas.height = img.clientHeight;
                if (cur.detections?.length > 0) drawAllBboxes(imageId, cur.detections);
                if (cur.selectedBbox) createBboxOverlay(imageId, cur.selectedBbox);
            }
        });
        resizeObserver.observe(img);
    };

    if (record.original_image_path) {
        img.src = '/' + record.original_image_path;
    }
}

function updateCardFromRecord(imageId, record) {
    const imageState = state.images.get(imageId);
    if (!imageState) return;

    const newResult = {
        id: record.id,
        manufacturer: record.manufacturer,
        model: record.model,
        year: record.year,
        confidence_score: record.confidence_score,
        matched_manufacturer_id: record.matched_manufacturer_id,
        matched_model_id: record.matched_model_id
    };

    if (['analysis_complete', 'verified'].includes(record.processing_stage)) {
        imageState.result = newResult;
        if (record.manufacturer && record.model) {
            imageState.status = 'completed';
            updateStatus(imageId, 'completed', '분석 완료');
            const editBtn = document.getElementById(`edit-btn-${imageId}`);
            if (editBtn) editBtn.style.display = '';
            const saveBtn = document.getElementById(`save-btn-${imageId}`);
            if (saveBtn) saveBtn.style.display = '';
        } else {
            imageState.status = 'analysis_error';
            updateStatus(imageId, 'error', 'null 인식 실패');
            const editBtn = document.getElementById(`edit-btn-${imageId}`);
            if (editBtn) editBtn.style.display = '';
        }
        displayResult(imageId, newResult);
        renderStats();
    } else if (record.processing_stage === 'yolo_detected' && record.yolo_detections) {
        imageState.detections = record.yolo_detections;
        imageState.status = 'detected';
        displayDetections(imageId, record.yolo_detections);
        renderStats();
    }
}

function startAnalyzeFeed() {
    // 탭별로 SSE 피드를 분리하여 각자의 source만 수신
    for (const source of ['file', 'folder']) {
        const es = new EventSource(`/api/analyze-feed?client_uuid=${CLIENT_UUID}&source=${source}`);
        es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.type === 'record_updated') {
                    const imageId = `db_${data.record.id}`;
                    if (state.images.has(imageId)) {
                        updateCardFromRecord(imageId, data.record);
                    }
                    // 새 레코드 (현재 탭 외부에서 생성)는 무시 (handleFiles에서 이미 처리)
                }
            } catch (err) {
                console.warn('analyze-feed 파싱 오류:', err);
            }
        };
        es.onerror = () => es.close();
    }
}

async function startVectorBatchDelete(source = 'file') {
    const tabLabel = source === 'folder' ? '폴더 감시' : '파일 선택';

    // DB 전체 개수 미리 조회
    let dbTotal = 0;
    try {
        const countResp = await fetch(`/api/pending-records?skip=0&limit=1&source=${source}&client_uuid=${CLIENT_UUID}&failure_only=true`);
        if (countResp.ok) ({ total: dbTotal } = await countResp.json());
    } catch (e) { /* 조회 실패 시 0 유지 */ }

    const liveCount = Array.from(state.images.values()).filter(img => img.source === source).length;
    const totalToDelete = Math.max(dbTotal, liveCount);

    if (totalToDelete === 0) {
        showToast('삭제할 이미지가 없습니다.', 'error');
        return;
    }

    if (!confirm(`⚠️ [${tabLabel}] 탭의 이미지 ${totalToDelete}개를 모두 삭제하시겠습니까?\n\nDB 레코드와 파일(원본 + 크롭)이 함께 삭제됩니다.\n삭제된 데이터는 복구할 수 없습니다.`)) return;

    const progressContainer = document.getElementById('vectorDeleteProgressContainer');
    const progressBar = document.getElementById('vectorDeleteProgressBar');
    const progressText = document.getElementById('vectorDeleteProgressText');
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    progressBar.textContent = '0%';
    let done = 0;

    const updateProgress = () => {
        const pct = totalToDelete > 0 ? Math.round((done / totalToDelete) * 100) : 100;
        progressBar.style.width = `${pct}%`;
        progressBar.textContent = `${pct}%`;
        progressText.textContent = `진행: ${done}/${totalToDelete}`;
    };

    // 1단계: DB 레코드 전체 페이지 순회 삭제
    let skip = 0;
    const pageSize = 50;
    while (true) {
        let items;
        try {
            const resp = await fetch(`/api/pending-records?skip=${skip}&limit=${pageSize}&source=${source}&client_uuid=${CLIENT_UUID}&failure_only=true`);
            if (!resp.ok) break;
            ({ items } = await resp.json());
        } catch (e) { break; }
        if (!items || items.length === 0) break;

        for (const record of items) {
            try {
                await fetch(`${API_BASE}/admin/review/${record.id}`, { method: 'DELETE' });
            } catch (e) {
                console.warn(`DB 삭제 실패 (id=${record.id}):`, e);
            }
            done++;
            updateProgress();
        }
        if (items.length < pageSize) break;
        skip += pageSize;
    }

    // 2단계: 라이브 세션 카드 중 DB에 없는 것(analyzedId 없음) 정리
    for (const [imageId, imageState] of Array.from(state.images.entries())) {
        if (imageState.source !== source) continue;
        if (manualDrawControllers.has(imageId)) {
            manualDrawControllers.get(imageId).abort();
            manualDrawControllers.delete(imageId);
        }
        const card = document.getElementById(`image-${imageId}`);
        if (card) card.remove();
        state.images.delete(imageId);
    }

    progressText.textContent = `✨ 완료! 페이지를 새로고침합니다...`;
    showToast(`${done}개 이미지 삭제 완료`, 'success');

    setTimeout(() => window.location.reload(), 1500);
}


//=============================================================================
// 폴더 자동 감시 (File System Access API — Chrome/Edge 전용)
//=============================================================================

async function startFolderWatch() {
    if (!window.showDirectoryPicker) {
        showToast('이 브라우저는 폴더 감시를 지원하지 않습니다. Chrome/Edge를 사용해주세요.', 'error');
        return;
    }

    try {
        const dirHandle = await window.showDirectoryPicker({ mode: 'readwrite' });

        // 상태 초기화
        folderWatch.dirHandle = dirHandle;
        folderWatch.seen.clear();
        folderWatch.queue = [];
        folderWatch.isProcessing = false;
        folderWatch.total = 0;
        folderWatch.processed = 0;

        // 폴더 세션 초기화: 이전 폴더의 이미지 카드 + 통계 리셋
        Array.from(state.images.keys()).forEach(id => {
            if (state.images.get(id)?.source === 'folder') {
                const card = document.getElementById(`image-${id}`);
                if (card) card.remove();
                state.images.delete(id);
            }
        });

        // 폴더 통계 초기화
        state.folderStats = { uploaded: 0, detected: 0, detectionFailed: 0, analyzed: 0, analysisError: 0 };
        localStorage.setItem(`reeve_folder_stats_${CLIENT_UUID}`, JSON.stringify(state.folderStats));

        // 폴더 하이드레이션 상태 초기화
        state.hydrateState.folder = { loading: false, page: 0, pageSize: 9, totalCount: 0 };

        renderStats();

        // 폴더 내 파일 빠른 스캔 (getFile() 없이 핸들만 수집 — 수만 개도 빠름)
        document.getElementById('folderWatchStatus').textContent = '폴더 스캔 중...';
        for await (const [name, handle] of dirHandle) {
            if (handle.kind !== 'file') continue;
            folderWatch.seen.add(name);
            folderWatch.queue.push({ name, handle });
        }
        folderWatch.total = folderWatch.queue.length;

        document.getElementById('folderWatchBtn').style.display = 'none';
        document.getElementById('folderStopBtn').style.display = 'inline-block';
        updateFolderWatchStatus();

        showToast(`폴더 감시 시작: ${dirHandle.name} (파일 ${folderWatch.total}개)`, 'success');

        // 배치 처리 시작 + 새 파일 폴링
        processBatchQueue();
        folderWatch.intervalId = setInterval(pollFolderForNewFiles, 3000);

    } catch (e) {
        if (e.name !== 'AbortError') {
            showToast('폴더 선택 실패: ' + e.message, 'error');
        }
    }
}

function stopFolderWatch() {
    if (folderWatch.intervalId) {
        clearInterval(folderWatch.intervalId);
        folderWatch.intervalId = null;
    }
    folderWatch.dirHandle = null;
    folderWatch.seen.clear();
    folderWatch.queue = [];
    folderWatch.isProcessing = false;

    document.getElementById('folderWatchBtn').style.display = 'inline-block';
    document.getElementById('folderStopBtn').style.display = 'none';
    document.getElementById('folderWatchStatus').textContent = '';

    showToast('폴더 감시 중지됨');
}

function updateFolderWatchStatus() {
    const el = document.getElementById('folderWatchStatus');
    if (!el || !folderWatch.dirHandle) return;
    const { queue, dirHandle } = folderWatch;
    const uploaded = state.folderStats.uploaded;
    if (queue.length > 0 || folderWatch.isProcessing) {
        el.textContent = `처리 중: ${uploaded}장 업로드 · 대기 ${queue.length}개`;
    } else {
        el.textContent = `감시 중: ${dirHandle.name} · ${uploaded}장 완료`;
    }
}

async function processBatchQueue() {
    if (folderWatch.isProcessing || folderWatch.queue.length === 0) return;

    folderWatch.isProcessing = true;
    const dirHandle = folderWatch.dirHandle;

    while (folderWatch.queue.length > 0 && folderWatch.dirHandle) {
        const batchSize = Math.max(1, parseInt(document.getElementById('batchSizeInput')?.value) || 10);
        const batch = folderWatch.queue.splice(0, batchSize);
        const imageFiles = [];

        // 이번 배치에서 이미지 파일만 필터 (여기서 getFile() 호출)
        for (const { name, handle } of batch) {
            try {
                const file = await handle.getFile();
                if (file.type.startsWith('image/')) {
                    imageFiles.push({ file, handle });
                }
            } catch (e) {
                console.warn('파일 읽기 실패:', name, e);
            }
        }

        if (imageFiles.length > 0) {
            await handleFiles(
                imageFiles.map(({ file }) => file),
                {
                    source: 'folder',
                    onEachUploadSuccess: async (file) => {
                        await dirHandle.removeEntry(file.name)
                            .catch(e => console.warn('로컬 파일 삭제 실패:', file.name, e));
                    }
                }
            );
        }

        folderWatch.processed += batch.length;
        updateFolderWatchStatus();
    }

    folderWatch.isProcessing = false;
    updateFolderWatchStatus();
}

async function pollFolderForNewFiles() {
    if (!folderWatch.dirHandle) return;

    let found = 0;
    try {
        for await (const [name, handle] of folderWatch.dirHandle) {
            if (folderWatch.seen.has(name) || handle.kind !== 'file') continue;
            folderWatch.seen.add(name);
            folderWatch.queue.push({ name, handle });
            folderWatch.total++;
            found++;
        }
    } catch (e) {
        console.warn('폴더 폴링 실패:', e);
        stopFolderWatch();
        showToast('폴더 접근 권한이 만료되었습니다. 다시 폴더를 선택해주세요.', 'error');
        return;
    }

    if (found > 0) {
        updateFolderWatchStatus();
        processBatchQueue();
    }
}

//=============================================================================
// 통계 초기화
//=============================================================================

function resetFileStats() {
    if (!confirm('파일 탭 통계를 초기화하시겠습니까?')) return;
    state.fileStats = { uploaded: 0, detected: 0, detectionFailed: 0, analyzed: 0, analysisError: 0, manuallyEdited: 0 };
    localStorage.setItem(`reeve_file_stats_${CLIENT_UUID}`, JSON.stringify(state.fileStats));
    renderStats();
}

function resetFolderStats() {
    if (!confirm('폴더 탭 통계를 초기화하시겠습니까?')) return;
    state.folderStats = { uploaded: 0, detected: 0, detectionFailed: 0, analyzed: 0, analysisError: 0 };
    localStorage.setItem(`reeve_folder_stats_${CLIENT_UUID}`, JSON.stringify(state.folderStats));
    renderStats();
}
