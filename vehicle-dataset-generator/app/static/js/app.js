/**
 * 메인 애플리케이션 로직
 * 전역 변수 및 기본 기능 관리
 */

// 전역 상태 관리
window.AppState = {
    selectedFiles: [],
    currentResults: null,
    currentPage: 1,
    itemsPerPage: 20,
    totalPages: 0,
    
    // 단일 이미지 바운딩 박스 관련
    canvas: null,
    ctx: null,
    currentImage: null,
    boundingBox: null,
    isDrawing: false,
    isDragging: false,
    dragOffset: { x: 0, y: 0 },
    detectedVehicles: [],
    autoDetectEnabled: true,
    
    // 다중 이미지 관련
    multiImageData: [],
    multiCurrentPage: 1,
    multiItemsPerPage: 6,
    multiTotalPages: 0
};

// API 엔드포인트 설정
window.API = {
    BASE_URL: '',
    ENDPOINTS: {
        // 분석 관련
        ANALYZE_TEXT: '/api/analysis/text',
        ANALYZE_SINGLE_IMAGE: '/api/analysis/image/single',
        DETECT_VEHICLES: '/api/analysis/vehicle/detect',
        DETECT_VEHICLES_MULTI: '/api/analysis/vehicle/detect/multi',
        ANALYZE_REGION: '/api/analysis/region/analyze',
        ANALYZE_MULTI: '/api/analysis/multi/analyze',
        CLEANUP_TEMP: '/api/analysis/temp/cleanup',
        
        // 데이터셋 관련
        SAVE_DATASET: '/api/dataset/save',
        DATASET_STATS: '/api/dataset/stats',
        
        // 기본
        TEMP_IMAGE: '/temp_image',
        HEALTH: '/health'
    }
};

// 유틸리티 함수들
window.Utils = {
    /**
     * 로딩 표시/숨김
     */
    showLoading(type) {
        const loadingDiv = document.getElementById(`${type}-loading`);
        if (loadingDiv) {
            loadingDiv.style.display = 'block';
        }
    },
    
    hideLoading(type) {
        const loadingDiv = document.getElementById(`${type}-loading`);
        if (loadingDiv) {
            loadingDiv.style.display = 'none';
        }
    },
    
    /**
     * 결과 표시/숨김
     */
    showResult(type) {
        const resultDiv = document.getElementById(`${type}-result`);
        if (resultDiv) {
            resultDiv.style.display = 'block';
        }
    },
    
    hideResult(type) {
        const resultDiv = document.getElementById(`${type}-result`);
        if (resultDiv) {
            resultDiv.style.display = 'none';
        }
    },
    
    /**
     * 에러 표시
     */
    displayError(type, message) {
        const resultDiv = document.getElementById(`${type}-result`);
        if (resultDiv) {
            resultDiv.innerHTML = `<div class="error">❌ ${message}</div>`;
            resultDiv.style.display = 'block';
        }
    },
    
    /**
     * 파일 크기 포맷팅
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },
    
    /**
     * 안전한 파일명 생성
     */
    sanitizeFilename(filename) {
        return filename.replace(/[^a-z0-9.-]/gi, '_').toLowerCase();
    },
    
    /**
     * API 요청 헬퍼
     */
    async apiRequest(endpoint, options = {}) {
        try {
            const response = await fetch(window.API.BASE_URL + endpoint, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('API 요청 오류:', error);
            throw error;
        }
    },
    
    /**
     * 스트리밍 응답 처리
     */
    async handleStreamResponse(endpoint, options, onData) {
        const response = await fetch(window.API.BASE_URL + endpoint, options);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop() || '';
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        onData(data);
                    } catch (e) {
                        console.warn('스트림 데이터 파싱 오류:', e);
                    }
                }
            }
        }
    }
};

// 탭 전환 함수
function switchTab(tabName) {
    // 탭 활성화
    document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
    document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');

    // 탭 컨텐츠 표시
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(`${tabName}-tab`).classList.add('active');
    
    // 상태 초기화
    clearFilesAndResult();
}

// 파일 및 결과 초기화
function clearFilesAndResult() {
    window.AppState.selectedFiles = [];
    window.AppState.currentResults = null;
    window.AppState.currentImage = null;
    window.AppState.boundingBox = null;
    window.AppState.detectedVehicles = [];
    window.AppState.multiImageData = [];
    window.AppState.multiCurrentPage = 1;
    window.AppState.multiTotalPages = 0;
    
    // UI 요소 초기화
    const filesList = document.getElementById('selected-files-list');
    const singleContainer = document.getElementById('single-image-container');
    const multiContainer = document.getElementById('multi-image-container');
    const imageResult = document.getElementById('image-result');
    const fileInput = document.getElementById('image-input');
    
    if (filesList) filesList.innerHTML = '';
    if (singleContainer) singleContainer.style.display = 'none';
    if (multiContainer) multiContainer.style.display = 'none';
    if (imageResult) {
        imageResult.innerHTML = '';
        imageResult.style.display = 'none';
    }
    if (fileInput) fileInput.value = '';
}

// 애플리케이션 초기화
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚗 차량 데이터셋 생성기 v2.0 시작');
    
    // 파일 드래그 앤 드롭 설정
    setupDragAndDrop();
    
    // 전역 에러 핸들러 설정
    window.addEventListener('error', function(e) {
        console.error('전역 에러:', e.error);
    });
    
    window.addEventListener('unhandledrejection', function(e) {
        console.error('처리되지 않은 Promise 거부:', e.reason);
    });
});

// 드래그 앤 드롭 설정
function setupDragAndDrop() {
    const fileUpload = document.querySelector('.file-upload');
    if (!fileUpload) return;
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        fileUpload.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });
    
    ['dragenter', 'dragover'].forEach(eventName => {
        fileUpload.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        fileUpload.addEventListener(eventName, unhighlight, false);
    });
    
    fileUpload.addEventListener('drop', handleDrop, false);
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    function highlight(e) {
        fileUpload.classList.add('dragover');
    }
    
    function unhighlight(e) {
        fileUpload.classList.remove('dragover');
    }
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0) {
            const fileInput = document.getElementById('image-input');
            if (fileInput) {
                fileInput.files = files;
                handleImageSelect({ target: { files: files } });
            }
        }
    }
}

// 이미지 선택 처리 (진입점)
function handleImageSelect(event) {
    const files = Array.from(event.target.files);
    if (files.length === 0) return;
    
    window.AppState.selectedFiles = files;
    
    if (files.length === 1) {
        // 단일 이미지 처리
        if (window.ImageAnalysis && window.ImageAnalysis.showSingleImageInterface) {
            window.ImageAnalysis.showSingleImageInterface(files[0]);
        }
        document.getElementById('multi-image-container').style.display = 'none';
        document.getElementById('single-image-container').style.display = 'block';
    } else {
        // 다중 이미지 처리
        if (window.ImageAnalysis && window.ImageAnalysis.showMultiImageInterface) {
            window.ImageAnalysis.showMultiImageInterface(files);
        }
        document.getElementById('single-image-container').style.display = 'none';
        document.getElementById('multi-image-container').style.display = 'block';
    }
    
    // 선택된 파일 목록 표시
    updateSelectedFilesList();
}

// 선택된 파일 목록 업데이트
function updateSelectedFilesList() {
    const listContainer = document.getElementById('selected-files-list');
    if (!listContainer) return;
    
    const files = window.AppState.selectedFiles;
    
    if (files.length === 0) {
        listContainer.innerHTML = '';
        return;
    }
    
    if (files.length === 1) {
        // 단일 이미지
        const file = files[0];
        listContainer.innerHTML = `
            <div style="margin: 10px 0; padding: 10px; background: #e8f4f8; border-radius: 8px; font-size: 0.9em;">
                <strong>선택된 파일:</strong> ${file.name} (${window.Utils.formatFileSize(file.size)})
            </div>
        `;
    } else {
        // 다중 이미지
        const fileList = files.map((file, index) =>
            `<div style="padding: 5px; background: #f0f0f0; margin: 2px; border-radius: 5px;">
                ${index + 1}. ${file.name} (${window.Utils.formatFileSize(file.size)})
            </div>`
        ).join('');

        listContainer.innerHTML = `
            <div style="margin: 10px 0; padding: 10px; background: #e8f4f8; border-radius: 8px;">
                <strong>선택된 파일 (${files.length}개):</strong>
                ${fileList}
            </div>
        `;
    }
}

// 텍스트 분석 함수
async function analyzeText() {
    const textInput = document.getElementById('text-input');
    if (!textInput) return;
    
    const text = textInput.value.trim();
    if (!text) {
        alert('분석할 텍스트를 입력해주세요.');
        return;
    }
    
    window.Utils.showLoading('text');
    window.Utils.hideResult('text');
    
    try {
        const result = await window.Utils.apiRequest(window.API.ENDPOINTS.ANALYZE_TEXT, {
            method: 'POST',
            body: JSON.stringify({ text: text })
        });
        
        window.Utils.hideLoading('text');
        
        if (result.error) {
            window.Utils.displayError('text', result.error);
        } else {
            displaySingleResult('text', result);
        }
        
    } catch (error) {
        window.Utils.hideLoading('text');
        window.Utils.displayError('text', '분석 중 오류가 발생했습니다: ' + error.message);
    }
}

// 단일 결과 표시 (기존 함수 유지)
function displaySingleResult(type, result) {
    const resultDiv = document.getElementById(`${type}-result`);
    window.AppState.currentResults = [result];

    if (result.error) {
        window.Utils.displayError(type, result.error);
        return;
    }

    const brandKr = result.brand_kr || 'N/A';
    const brandEn = result.brand_en || 'N/A';
    const modelKr = result.model_kr || 'N/A';
    const modelEn = result.model_en || 'N/A';
    const year = result.year || 'N/A';
    const yearInfo = result.year_info || 'N/A';
    const confidence = result.confidence || 0;
    const bboxUsed = result.bbox_used || null;
    const cropped = result.cropped || false;

    resultDiv.innerHTML = `
        <h3>🎯 ${cropped ? '영역' : '전체'} 분석 결과</h3>
        ${bboxUsed ? `<div style="background: #e8f5e8; padding: 10px; border-radius: 6px; margin-bottom: 15px; font-size: 0.9em;">
            <strong>분석 영역:</strong> ${bboxUsed.join(', ')} ${cropped ? '(크롭됨)' : '(전체)'}
        </div>` : ''}
        
        <div class="editable-fields" style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
            <div>
                <div style="margin-bottom: 15px;">
                    <label style="display: block; font-weight: 600; margin-bottom: 5px; color: #333;">🏷️ 브랜드 (한글)</label>
                    <input type="text" class="field-input" data-field="brand_kr" value="${brandKr}" data-index="0" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
                </div>
                <div style="margin-bottom: 15px;">
                    <label style="display: block; font-weight: 600; margin-bottom: 5px; color: #333;">🏷️ 브랜드 (영문)</label>
                    <input type="text" class="field-input" data-field="brand_en" value="${brandEn}" data-index="0" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
                </div>
                <div style="margin-bottom: 15px;">
                    <label style="display: block; font-weight: 600; margin-bottom: 5px; color: #333;">🚗 차종 (한글)</label>
                    <input type="text" class="field-input" data-field="model_kr" value="${modelKr}" data-index="0" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
                </div>
            </div>
            <div>
                <div style="margin-bottom: 15px;">
                    <label style="display: block; font-weight: 600; margin-bottom: 5px; color: #333;">🚗 차종 (영문)</label>
                    <input type="text" class="field-input" data-field="model_en" value="${modelEn}" data-index="0" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
                </div>
                <div style="margin-bottom: 15px;">
                    <label style="display: block; font-weight: 600; margin-bottom: 5px; color: #333;">📅 연식</label>
                    <input type="text" class="field-input" data-field="year" value="${year}" data-index="0" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
                </div>
                <div style="margin-bottom: 15px;">
                    <label style="display: block; font-weight: 600; margin-bottom: 5px; color: #333;">📊 신뢰도 (%)</label>
                    <input type="number" class="field-input" data-field="confidence" value="${confidence}" data-index="0" min="0" max="100" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
                </div>
            </div>
        </div>
        
        <div style="margin-bottom: 20px;">
            <label style="display: block; font-weight: 600; margin-bottom: 5px; color: #333;">📋 연식 근거/추가정보</label>
            <textarea class="field-input" data-field="year_info" data-index="0" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; min-height: 80px; resize: vertical; font-size: 14px; font-family: inherit;" placeholder="연식 판단 근거나 추가 정보를 입력하세요...">${yearInfo}</textarea>
        </div>
        
        <div class="json-result">
            <strong>JSON 결과:</strong><br>
            <pre>${JSON.stringify(result, null, 2)}</pre>
        </div>
    `;

    resultDiv.style.display = 'block';
    
    // 입력 필드 변경 감지 추가
    addFieldChangeListeners();
}

// 입력 필드 변경 감지
function addFieldChangeListeners() {
    const inputs = document.querySelectorAll('.field-input');
    inputs.forEach(input => {
        input.addEventListener('input', function() {
            updateCurrentResults();
        });
    });
}

// 현재 결과 업데이트
function updateCurrentResults() {
    if (!window.AppState.currentResults) return;
    
    const inputs = document.querySelectorAll('.field-input');
    inputs.forEach(input => {
        const index = parseInt(input.dataset.index);
        const field = input.dataset.field;
        
        if (window.AppState.currentResults[index] && !window.AppState.currentResults[index].error) {
            let value = input.value;
            
            // 숫자 필드 처리
            if (field === 'confidence') {
                value = parseInt(value) || 0;
            }
            
            window.AppState.currentResults[index][field] = value;
        }
    });
}

// 전역 함수들 (기존 호환성 유지)
window.switchTab = switchTab;
window.handleImageSelect = handleImageSelect;
window.analyzeText = analyzeText;
window.clearFilesAndResult = clearFilesAndResult;
window.displaySingleResult = displaySingleResult;
window.addFieldChangeListeners = addFieldChangeListeners;
window.updateCurrentResults = updateCurrentResults;
