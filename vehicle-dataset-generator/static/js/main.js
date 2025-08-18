document.addEventListener('DOMContentLoaded', function() {
    let uploadedFiles = [];
    let manufacturers = [];
    let analysisResults = [];
    let bboxHandlers = {}; // 파일 경로별 BoundingBoxHandler 저장

    // 페이지 로드시 초기화
    loadDatasetStatistics();
    loadManufacturers();

    // 파일 업로드 이벤트
    const uploadBtn = document.getElementById('uploadBtn');
    if (uploadBtn) {
        uploadBtn.addEventListener('click', function() {
            const fileInput = document.getElementById('fileInput');
            const files = fileInput.files;

            if (files.length === 0) {
                showAlert('파일을 선택해주세요.', 'warning');
                return;
            }

            uploadFiles(files);
        });
    }

    // 배치 분석 버튼 이벤트
    const batchAnalysisBtn = document.getElementById('batchAnalysisBtn');
    if (batchAnalysisBtn) {
        batchAnalysisBtn.addEventListener('click', function() {
            if (uploadedFiles.length === 0) {
                showAlert('분석할 이미지가 없습니다.', 'warning');
                return;
            }

            startBatchAnalysis();
        });
    }

    // 제조사 선택 변경 이벤트
    const manufacturerSelect = document.getElementById('manufacturerSelect');
    const modelMfgSelect = document.getElementById('modelMfgSelect');

    if (manufacturerSelect) {
        manufacturerSelect.addEventListener('change', function() {
            const manufacturerCode = this.value;
            const modelSelect = document.getElementById('modelSelect');

            if (manufacturerCode && modelSelect) {
                loadModels(manufacturerCode, modelSelect);
            } else if (modelSelect) {
                modelSelect.innerHTML = '<option value="">먼저 제조사를 선택하세요</option>';
            }
        });
    }

    if (modelMfgSelect) {
        modelMfgSelect.addEventListener('change', function() {
            const manufacturerCode = this.value;
            const modelSelect = document.getElementById('modelSelect');

            if (manufacturerCode && modelSelect) {
                loadModels(manufacturerCode, modelSelect);
            } else if (modelSelect) {
                modelSelect.innerHTML = '<option value="">먼저 제조사를 선택하세요</option>';
            }
        });
    }

    // 수동 입력 저장
    const saveManualInputBtn = document.getElementById('saveManualInput');
    if (saveManualInputBtn) {
        saveManualInputBtn.addEventListener('click', function() {
            saveManualInput();
        });
    }

    // 새 카테고리 저장
    const saveCategoryBtn = document.getElementById('saveCategoryBtn');
    if (saveCategoryBtn) {
        saveCategoryBtn.addEventListener('click', function() {
            const activeTab = document.querySelector('.nav-tabs .nav-link.active');

            if (activeTab && activeTab.id === 'manufacturer-tab') {
                saveNewManufacturer();
            } else {
                saveNewModel();
            }
        });
    }

    // 파일 업로드 함수
    function uploadFiles(files) {
        const formData = new FormData();

        for (let i = 0; i < files.length; i++) {
            formData.append('files', files[i]);
        }

        fetch('/api/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                uploadedFiles = uploadedFiles.concat(data.files);
                displayUploadedImages(data.files);
                const batchSection = document.getElementById('batchAnalysisSection');
                if (batchSection) {
                    batchSection.style.display = 'block';
                }
                showAlert(`${data.files.length}개 파일이 업로드되었습니다.`, 'success');
            } else {
                showAlert('업로드 실패: ' + data.message, 'danger');
            }
        })
        .catch(error => {
            showAlert('업로드 중 오류가 발생했습니다.', 'danger');
        });
    }

    // 업로드된 이미지 표시
    function displayUploadedImages(files) {
        const imageContainer = document.getElementById('imageContainer');
        if (!imageContainer) return;

        files.forEach(function(file) {
            const col = document.createElement('div');
            col.className = 'col-md-6 mb-3';
            col.dataset.filePath = file.file_path;

            // 카드 구조 생성
            const card = document.createElement('div');
            card.className = 'card';

            const cardBody = document.createElement('div');
            cardBody.className = 'card-body text-center';

            // 이미지 컨테이너 생성
            const imageWrapper = document.createElement('div');
            imageWrapper.className = 'position-relative mb-2';
            imageWrapper.style.display = 'inline-block';

            // 이미지 요소 생성
            const img = document.createElement('img');
            img.className = 'img-fluid';
            img.style.maxWidth = '100%';
            img.style.height = 'auto';
            img.style.border = '1px solid #ddd';
            img.src = file.file_path;
            img.alt = file.original_name;

            // 제목
            const title = document.createElement('h6');
            title.className = 'card-title';
            title.textContent = file.original_name;

            // 버튼 그룹
            const btnGroup = document.createElement('div');
            btnGroup.className = 'btn-group';
            btnGroup.setAttribute('role', 'group');

            const detectBtn = document.createElement('button');
            detectBtn.type = 'button';
            detectBtn.className = 'btn btn-sm btn-primary detect-btn';
            detectBtn.innerHTML = '<i class="bi bi-search"></i> 탐지';

            // 결과 컨테이너들
            const detectionResult = document.createElement('div');
            detectionResult.className = 'detection-result mt-2';
            detectionResult.style.display = 'none';

            const analysisResult = document.createElement('div');
            analysisResult.className = 'analysis-result mt-2';
            analysisResult.style.display = 'none';

            // 요소들 조립
            imageWrapper.appendChild(img);
            btnGroup.appendChild(detectBtn);
            cardBody.appendChild(imageWrapper);
            cardBody.appendChild(title);
            cardBody.appendChild(btnGroup);
            cardBody.appendChild(detectionResult);
            cardBody.appendChild(analysisResult);
            card.appendChild(cardBody);
            col.appendChild(card);

            imageContainer.appendChild(col);

            // 탐지 버튼 이벤트
            detectBtn.addEventListener('click', function() {
                const filePath = col.dataset.filePath;
                detectVehicles(filePath, this);
                });

            // 자동 탐지 실행
            const filePath = col.dataset.filePath;
            detectVehicles(filePath, detectBtn);
        });
    }

    // 차량 탐지
    function detectVehicles(filePath, button) {
        button.disabled = true;
        button.innerHTML = '<i class="bi bi-hourglass-split"></i> 탐지중...';

        fetch('/api/detect', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ file_path: filePath })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                displayDetectionResults(filePath, data.vehicles);
                showAlert('차량 탐지가 완료되었습니다.', 'success');
            } else {
                showAlert('탐지 실패: ' + data.message, 'danger');
            }
        })
        .catch(error => {
            showAlert('탐지 중 오류가 발생했습니다.', 'danger');
        })
        .finally(() => {
            button.disabled = false;
            button.innerHTML = '<i class="bi bi-search"></i> 탐지';
        });
    }

    // 탐지 결과 표시
    function displayDetectionResults(filePath, vehicles) {
        const container = document.querySelector(`[data-file-path="${filePath}"] .detection-result`);
        const imageElement = document.querySelector(`[data-file-path="${filePath}"] img`);
        if (!container || !imageElement) return;

        // 차량이 탐지되지 않은 경우 기본 바운딩 박스 생성
        if (vehicles.length === 0) {
            // 이미지 크기 정보가 필요하므로 이미지 로드 후 처리
            const createDefaultBbox = () => {
                const naturalWidth = imageElement.naturalWidth || imageElement.offsetWidth;
                const naturalHeight = imageElement.naturalHeight || imageElement.offsetHeight;

                // 기본 바운딩 박스 생성 (이미지 중앙에 50% 크기, 절대 좌표)
                const centerX = naturalWidth / 2;
                const centerY = naturalHeight / 2;
                const width = naturalWidth * 0.5;
                const height = naturalHeight * 0.5;

                const defaultVehicle = {
                    class_name: 'vehicle',
                    confidence: 0.0,
                    bbox: [
                        centerX - width/2,  // x1
                        centerY - height/2, // y1
                        centerX + width/2,  // x2
                        centerY + height/2  // y2
                    ]
                };
                vehicles = [defaultVehicle];

                console.log('기본 바운딩 박스 생성:', {
                    naturalWidth,
                    naturalHeight,
                    bbox: defaultVehicle.bbox
                });

                // 바운딩 박스 핸들러 생성 및 UI 업데이트 진행
                proceedWithBboxHandler();
            };

            // 이미지가 로드되었는지 확인
            if (imageElement.complete && imageElement.naturalWidth > 0) {
                createDefaultBbox();
                return; // 여기서 함수 종료
            } else {
                imageElement.onload = createDefaultBbox;
                return; // 여기서 함수 종료
            }
        } else {
          vehicles = [vehicles[0]]; // 정확도가 가장 높은 한개만
        }

        // 바운딩 박스 핸들러 생성 및 UI 업데이트
        proceedWithBboxHandler();

        function proceedWithBboxHandler() {

        // 바운딩 박스 핸들러 생성
        let bboxHandler = null;

        // 이미지가 로드된 후 바운딩 박스 생성
        const createBboxHandler = () => {
            console.log('바운딩 박스 핸들러 생성 시도:', imageElement, vehicles);
            console.log('이미지 정보:', {
                complete: imageElement.complete,
                naturalWidth: imageElement.naturalWidth,
                naturalHeight: imageElement.naturalHeight,
                offsetWidth: imageElement.offsetWidth,
                offsetHeight: imageElement.offsetHeight
            });

            if (bboxHandler) {
                bboxHandler.destroy();
                bboxHandler = null;
            }

            // 이미지가 완전히 로드되었는지 확인
            if (imageElement.naturalWidth === 0 || imageElement.naturalHeight === 0) {
                console.log('이미지가 아직 로드되지 않음, 대기 중...');
                setTimeout(createBboxHandler, 100);
                return;
            }

            try {
                bboxHandler = new BoundingBoxHandler(imageElement, vehicles, (updatedVehicles) => {
                    // 바운딩 박스 변경시 콜백
                    console.log('바운딩 박스가 업데이트되었습니다:', updatedVehicles);
                });
                console.log('바운딩 박스 핸들러 생성 성공:', bboxHandler);
                
                // 전역 객체에 저장
                bboxHandlers[filePath] = bboxHandler;
            } catch (error) {
                console.error('바운딩 박스 핸들러 생성 실패:', error);
            }
        };

        // 이미지 로드 상태 확인 및 핸들러 생성
        if (imageElement.complete && imageElement.naturalWidth > 0) {
            // 약간의 지연을 두고 실행 (DOM 업데이트 완료 대기)
            setTimeout(createBboxHandler, 50);
        } else {
            imageElement.onload = () => {
                setTimeout(createBboxHandler, 50);
            };

            // 이미지 로드 실패시 대비
            imageElement.onerror = () => {
                console.error('이미지 로드 실패:', imageElement.src);
            };
        }

        let html = vehicles.length > 0 && vehicles[0].confidence > 0
            ? '<h6>탐지된 차량:</h6>'
            : '<h6>기본 바운딩 박스:</h6><p class="text-muted small">탐지된 차량이 없어 기본 바운딩 박스를 생성했습니다. 바운딩 박스를 수정한 후 분석해주세요.</p>';

        vehicles.forEach(function(vehicle, index) {
            const isDefault = vehicle.confidence === 0.0;
            const confidenceText = isDefault ? '기본' : `${(vehicle.confidence * 100).toFixed(1)}%`;
            const badgeClass = isDefault ? 'bg-secondary' : 'bg-primary';

            html += `
                <div class="alert alert-info alert-sm">
                    <strong>${vehicle.class_name}</strong> 
                    <span class="badge ${badgeClass} confidence-badge">${confidenceText}</span>
                    <br>
                    <small>위치: [${vehicle.bbox.join(', ')}]</small>
                    <br>
                    <button type="button" class="btn btn-sm btn-success analyze-btn mt-1" 
                            data-file-path="${filePath}" data-bbox='${JSON.stringify(vehicle.bbox)}' data-index="${index}">
                        <i class="bi bi-gear"></i> 분석
                    </button>
                </div>
            `;
        });

        container.innerHTML = html;
        container.style.display = 'block';

        // 분석 버튼 이벤트
        const analyzeButtons = container.querySelectorAll('.analyze-btn');
        analyzeButtons.forEach(btn => {
            btn.addEventListener('click', function() {
                const filePath = this.dataset.filePath;
                const vehicleIndex = parseInt(this.dataset.index);
                const vehicle = vehicles[vehicleIndex];

                // 바운딩 박스 핸들러에서 최신 바운딩 박스 정보 가져오기
                let currentBbox = vehicle.bbox;
                if (bboxHandler && bboxHandler.getBoundingBoxes) {
                    const boxes = bboxHandler.getBoundingBoxes();
                    if (boxes[vehicleIndex]) {
                        currentBbox = boxes[vehicleIndex];
                    }
                }

                analyzeVehicle(filePath, currentBbox, this, bboxHandler);
            });
        });
        }
    }

    // 최신 바운딩 박스 좌표 사용
    // 차량 분석 (스트리밍)
    function analyzeVehicle(filePath, bbox, button, bboxHandler) {
        button.disabled = true;
        button.innerHTML = '<i class="bi bi-hourglass-split"></i> 분석중...';

        // 진행 표시를 위한 컨테이너 찾기
        const container = document.querySelector(`[data-file-path="${filePath}"] .analysis-result`);

        // 스트리밍 분석 시작
        fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                file_path: filePath,
                bbox: bbox
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('네트워크 응답이 정상이 아닙니다.');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            function readStream() {
                return reader.read().then(({done, value}) => {
                    if (done) {
                        console.log('스트리밍 완료');
                        return;
                    }

                    // 수신된 데이터 디코딩
                    const chunk = decoder.decode(value, {stream: true});
                    const lines = chunk.split('\n');

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.substring(6));
                                handleAnalysisProgress(filePath, data, button, container);
                            } catch (e) {
                                console.error('데이터 파싱 오류:', e);
                            }
                        }
                    }

                    // 다음 데이터 읽기
                    return readStream();
                });
            }

            return readStream();
        })
        .catch(error => {
            console.error('분석 오류:', error);
            showAlert('분석 중 오류가 발생했습니다.', 'danger');
            button.disabled = false;
            button.innerHTML = '<i class="bi bi-gear"></i> 분석';
        });
    }

    // 분석 진행 상황 처리
    function handleAnalysisProgress(filePath, data, button, container) {
        console.log('분석 진행:', data);

        switch (data.status) {
            case 'started':
                showProgressMessage(container, data.message, data.progress);
                break;

            case 'analyzing_manufacturer':
                showProgressMessage(container, data.message, data.progress);
                break;

            case 'manufacturer_completed':
                showProgressMessage(container, data.message, data.progress);
                // 제조사 정보 표시
                updatePartialResult(container, data, 'manufacturer');
                break;

            case 'waiting':
                showProgressMessage(container, data.message, data.progress);
                break;

            case 'analyzing_model':
                showProgressMessage(container, data.message, data.progress);
                break;

            case 'success':
                // 최종 결과 표시
                displayAnalysisResult(filePath, data);
                button.disabled = false;
                button.innerHTML = '<i class="bi bi-gear"></i> 분석';
                showAlert('차량 분석이 완료되었습니다.', 'success');
                break;

            case 'partial_success':
                // 부분 성공 결과 표시
                displayPartialAnalysisResult(filePath, data);
                button.disabled = false;
                button.innerHTML = '<i class="bi bi-gear"></i> 분석';
                showAlert('제조사는 식별되었지만 모델 분석에 실패했습니다.', 'warning');
                break;

            case 'error':
                showAlert('분석 오류: ' + data.message, 'danger');
                button.disabled = false;
                button.innerHTML = '<i class="bi bi-gear"></i> 분석';
                break;
        }
    }

    // 진행 메시지 표시
    function showProgressMessage(container, message, progress) {
        const html = `
            <div class="alert alert-info">
                <div class="d-flex justify-content-between align-items-center">
                    <span>${message}</span>
                    <span class="badge bg-primary">${progress}%</span>
                </div>
                <div class="progress mt-2">
                    <div class="progress-bar" role="progressbar" style="width: ${progress}%"></div>
                </div>
            </div>
        `;
        container.innerHTML = html;
        container.style.display = 'block';
    }

    // 부분 결과 업데이트
    function updatePartialResult(container, data, type) {
        if (type === 'manufacturer' && data.manufacturer_code) {
            const manufacturerInfo = `
                <div class="mt-2">
                    <h6>제조사 식별 완료:</h6>
                    <p><strong>제조사:</strong> ${data.manufacturer_korean_name}(${data.manufacturer_english_name}) 
                       <span class="badge bg-success confidence-badge">${(data.manufacturer_confidence * 100).toFixed(1)}%</span></p>
                </div>
            `;
            container.innerHTML += manufacturerInfo;
        }
    }

    // 부분 성공 결과 표시
    function displayPartialAnalysisResult(filePath, result) {
        const container = document.querySelector(`[data-file-path="${filePath}"] .analysis-result`);
        if (!container) return;

        const html = `
            <div class="analysis-result">
                <h6>분석 결과 (부분):</h6>
                <p><strong>제조사:</strong> ${result.manufacturer_korean_name}(${result.manufacturer_english_name}) 
                   <span class="badge bg-success confidence-badge">${(result.manufacturer_confidence * 100).toFixed(1)}%</span></p>
                <p class="text-warning"><strong>모델:</strong> 식별 실패</p>
                <button type="button" class="btn btn-sm btn-secondary manual-retry-btn mt-1">
                    <i class="bi bi-pencil"></i> 수동 입력
                </button>
            </div>
        `;
        container.innerHTML = html;
        container.style.display = 'block';

        // 수동 입력 버튼 이벤트
        const manualRetryBtn = container.querySelector('.manual-retry-btn');
        if (manualRetryBtn) {
            manualRetryBtn.addEventListener('click', function() {
                showManualInputModal(filePath);
            });
        }
    }

    // 분석 결과 표시
    function displayAnalysisResult(filePath, result) {
        const container = document.querySelector(`[data-file-path="${filePath}"] .analysis-result`);
        if (!container) return;

        if (result.status === 'success') {
          container.innerHTML = `
                <div class="analysis-result">
                    <h6>분석 결과:</h6>
                    <p><strong>제조사:</strong> ${result.manufacturer_korean_name}(${result.manufacturer_english_name}) 
                       <span class="badge bg-success confidence-badge">${(result.manufacturer_confidence * 100).toFixed(
              1)}%</span></p>
                    <p><strong>모델:</strong> ${result.model_korean_name}(${result.model_english_name}) 
                       <span class="badge bg-success confidence-badge">${(result.model_confidence * 100).toFixed(
              1)}%</span></p>
                    <button type="button" class="btn btn-sm btn-primary save-dataset-btn" 
                            data-file-path="${filePath}" data-result='${JSON.stringify(result)}'>
                        <i class="bi bi-save"></i> 데이터셋 저장
                    </button>
                    <button type="button" class="btn btn-sm btn-secondary mt-1 manual-retry-btn">
                        <i class="bi bi-pencil"></i> 수동 입력
                    </button>
                </div>
            `;
            container.style.display = 'block';

            // 저장 버튼 이벤트
            const saveBtn = container.querySelector('.save-dataset-btn');
            if (saveBtn) {
                saveBtn.addEventListener('click', function() {
                    const filePath = this.dataset.filePath;
                    const result = JSON.parse(this.dataset.result);
                    saveToDataset(filePath, result, this);
                });
            }

            // 수동 입력 버튼 이벤트
            const manualRetryBtn = container.querySelector('.manual-retry-btn');
            if (manualRetryBtn) {
                manualRetryBtn.addEventListener('click', function() {
                    showManualInputModal(filePath);
                });
            }
        } else {
            container.innerHTML = `
                <div class="alert alert-warning">
                    <strong>분석 실패:</strong> ${result.message}
                    <br>
                    <button type="button" class="btn btn-sm btn-secondary mt-1 manual-retry-btn">
                        <i class="bi bi-pencil"></i> 수동 입력
                    </button>
                </div>
            `;
            container.style.display = 'block';

            // 수동 입력 버튼 이벤트
            const manualRetryBtn = container.querySelector('.manual-retry-btn');
            if (manualRetryBtn) {
                manualRetryBtn.addEventListener('click', function() {
                    showManualInputModal(filePath);
                });
            }
        }
    }

    // 배치 분석 시작
    function startBatchAnalysis() {
        const button = document.getElementById('batchAnalysisBtn');
        if (!button) return;

        button.disabled = true;
        button.innerHTML = '<i class="bi bi-hourglass-split"></i> 분석 중...';

        // 각 이미지의 최신 바운딩 박스 정보 수집
        const images = [];
        
        uploadedFiles.forEach(file => {
            const filePath = file.file_path;
            let bbox = [0, 0, 100, 100]; // 기본값
            
            // 저장된 BoundingBoxHandler에서 최신 바운딩 박스 정보 가져오기
            if (bboxHandlers[filePath] && bboxHandlers[filePath].getBoundingBoxes) {
                try {
                    const boxes = bboxHandlers[filePath].getBoundingBoxes();
                    if (boxes && boxes.length > 0) {
                        bbox = boxes[0]; // 첫 번째 바운딩 박스 사용
                    }
                } catch (error) {
                    console.warn('바운딩 박스 정보 가져오기 실패, 기본값 사용:', filePath, error);
                }
            } else {
                // BoundingBoxHandler가 없는 경우 분석 버튼의 data-bbox에서 가져오기
                const imageContainer = document.querySelector(`[data-file-path="${filePath}"]`);
                if (imageContainer) {
                    const analyzeBtn = imageContainer.querySelector('.analyze-btn');
                    if (analyzeBtn && analyzeBtn.dataset.bbox) {
                        try {
                            bbox = JSON.parse(analyzeBtn.dataset.bbox);
                            console.log('분석 버튼에서 바운딩 박스 정보 가져옴:', filePath, bbox);
                        } catch (error) {
                            console.warn('분석 버튼 바운딩 박스 파싱 실패, 기본값 사용:', filePath, error);
                        }
                    }
                }
            }
            
            images.push({
                file_path: filePath,
                bbox: bbox
            });
        });

        console.log('배치 분석 요청 데이터:', images);

        // 스트리밍 배치 분석 시작
        fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ images: images })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('네트워크 응답이 정상이 아닙니다.');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            function readStream() {
                return reader.read().then(({done, value}) => {
                    if (done) {
                        console.log('배치 분석 스트리밍 완료');
                        button.disabled = false;
                        button.innerHTML = '<i class="bi bi-gear"></i> 전체 이미지 분석 시작';
                        showAlert('배치 분석이 완료되었습니다.', 'success');
                        return;
                    }

                    // 수신된 데이터 디코딩
                    const chunk = decoder.decode(value, {stream: true});
                    const lines = chunk.split('\n');

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.substring(6));
                                handleBatchAnalysisProgress(data);
                            } catch (e) {
                                console.error('배치 분석 데이터 파싱 오류:', e);
                            }
                        }
                    }

                    // 다음 데이터 읽기
                    return readStream();
                });
            }

            return readStream();
        })
        .catch(error => {
            console.error('배치 분석 오류:', error);
            showAlert('배치 분석 중 오류가 발생했습니다.', 'danger');
            button.disabled = false;
            button.innerHTML = '<i class="bi bi-gear"></i> 전체 이미지 분석 시작';
        });
    }

    // 배치 분석 진행 상황 처리
    function handleBatchAnalysisProgress(data) {
        console.log('배치 분석 진행:', data);
        
        const filePath = data.file_path;
        
        // 해당 이미지의 컨테이너 찾기
        const container = document.querySelector(`[data-file-path="${filePath}"] .analysis-result`);
        
        if (!container) {
            console.warn('이미지 컨테이너를 찾을 수 없습니다:', filePath);
            return;
        }

        switch (data.status) {
            case 'batch_started':
                showAlert(data.message, 'info');
                break;

            case 'analyzing':
                showAlert(`${data.message}\n파일명: ${data.file_path}`, 'info');
                break;

            case 'started':
            case 'analyzing_manufacturer':
            case 'waiting':
            case 'analyzing_model':
                showProgressMessage(container, data.message, data.progress);
                break;

            case 'manufacturer_completed':
                showProgressMessage(container, data.message, data.progress);
                updatePartialResult(container, data, 'manufacturer');
                break;
            case 'success':
                // 개별 이미지 분석 성공
                displayAnalysisResult(filePath, data);
                showAlert(data.message, 'success');
                break;

            case 'partial_success':
                // 개별 이미지 부분 성공
                displayPartialAnalysisResult(filePath, data);
                showAlert(data.message, 'warning');
                break;

            case 'error':
                // 개별 이미지 분석 오류
                container.innerHTML = `
                    <div class="alert alert-danger">
                        <strong>분석 실패:</strong> ${data.message}
                        <br>
                        <button type="button" class="btn btn-sm btn-secondary mt-1 manual-retry-btn">
                            <i class="bi bi-pencil"></i> 수동 입력
                        </button>
                    </div>
                `;
                container.style.display = 'block';
                
                // 수동 입력 버튼 이벤트
                const manualRetryBtn = container.querySelector('.manual-retry-btn');
                if (manualRetryBtn) {
                    manualRetryBtn.addEventListener('click', function() {
                        showManualInputModal(filePath);
                    });
                }
                
                showAlert(data.message, 'danger');
                break;

            case 'all_completed':
                showAlert(data.message, 'success');
                break;

            case 'batch_error':
                showAlert('배치 분석 오류: ' + data.message, 'danger');
                break;
        }
    }
    function saveToDataset(filePath, result, button) {
        button.disabled = true;
        button.innerHTML = '<i class="bi bi-hourglass-split"></i> 저장중...';

        fetch('/api/save-dataset', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                file_path: filePath,
                manufacturer_code: result.manufacturer_code,
                model_code: result.model_code,
                manufacturer_confidence: result.manufacturer_confidence,
                model_confidence: result.model_confidence,
                bbox: result.bbox,
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showAlert('데이터셋에 저장되었습니다.', 'success');
                button.classList.remove('btn-primary');
                button.classList.add('btn-success');
                button.innerHTML = '<i class="bi bi-check"></i> 저장완료';
                loadDatasetStatistics(); // 통계 업데이트
            } else {
                showAlert('저장 실패: ' + data.message, 'danger');
                button.disabled = false;
                button.innerHTML = '<i class="bi bi-save"></i> 데이터셋 저장';
            }
        })
        .catch(error => {
            showAlert('저장 중 오류가 발생했습니다.', 'danger');
            button.disabled = false;
            button.innerHTML = '<i class="bi bi-save"></i> 데이터셋 저장';
        });
    }

    // 수동 입력 모달 표시
    function showManualInputModal(filePath) {
        const modalImagePath = document.getElementById('modalImagePath');
        const manufacturerSelect = document.getElementById('manufacturerSelect');
        const modelSelect = document.getElementById('modelSelect');
        const modal = document.getElementById('manualInputModal');

        if (modalImagePath) modalImagePath.value = filePath;
        if (manufacturerSelect) manufacturerSelect.value = '';
        if (modelSelect) modelSelect.innerHTML = '<option value="">먼저 제조사를 선택하세요</option>';

        if (modal && window.bootstrap) {
            const bsModal = new bootstrap.Modal(modal);
            bsModal.show();
        }
    }

    // 수동 입력 저장
    function saveManualInput() {
        const modalImagePath = document.getElementById('modalImagePath');
        const manufacturerSelect = document.getElementById('manufacturerSelect');
        const modelSelect = document.getElementById('modelSelect');

        if (!modalImagePath || !manufacturerSelect || !modelSelect) return;

        const filePath = modalImagePath.value;
        const manufacturerCode = manufacturerSelect.value;
        const modelCode = modelSelect.value;

        if (!manufacturerCode || !modelCode) {
            showAlert('제조사와 모델을 모두 선택해주세요.', 'warning');
            return;
        }

        const result = {
            manufacturer_code: manufacturerCode,
            model_code: modelCode,
            manufacturer_confidence: 1.0,
            model_confidence: 1.0
        };

        // 제조사와 모델 정보 추가
        const manufacturer = manufacturers.find(m => m.code === manufacturerCode);
        if (manufacturer) {
            result.manufacturer_english_name = manufacturer.english_name;
            result.manufacturer_korean_name = manufacturer.korean_name;
        }

        // 모델 정보는 별도 API 호출로 가져와야 함 (간단히 구현)
        result.model_english_name = modelCode;
        result.model_korean_name = modelCode;

        const saveBtn = document.getElementById('saveManualInput');
        saveToDataset(filePath, result, saveBtn);

        const modal = document.getElementById('manualInputModal');
        if (modal && window.bootstrap) {
            const bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) bsModal.hide();
        }
    }

    // 새 제조사 저장
    function saveNewManufacturer() {
        const mfgCode = document.getElementById('mfgCode');
        const mfgEnglishName = document.getElementById('mfgEnglishName');
        const mfgKoreanName = document.getElementById('mfgKoreanName');
        const isDomestic = document.getElementById('isDomestic');

        if (!mfgCode || !mfgEnglishName || !mfgKoreanName || !isDomestic) return;

        const data = {
            code: mfgCode.value,
            english_name: mfgEnglishName.value,
            korean_name: mfgKoreanName.value,
            is_domestic: isDomestic.checked
        };

        fetch('/api/add-manufacturer', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showAlert('새 제조사가 추가되었습니다.', 'success');
                const modal = document.getElementById('addCategoryModal');
                if (modal && window.bootstrap) {
                    const bsModal = bootstrap.Modal.getInstance(modal);
                    if (bsModal) bsModal.hide();
                }
                loadManufacturers(); // 제조사 목록 새로고침
            } else {
                showAlert('추가 실패: ' + data.message, 'danger');
            }
        })
        .catch(error => {
            showAlert('제조사 추가 중 오류가 발생했습니다.', 'danger');
        });
    }

    // 새 모델 저장
    function saveNewModel() {
        const modelCode = document.getElementById('modelCode');
        const modelMfgSelect = document.getElementById('modelMfgSelect');
        const modelEnglishName = document.getElementById('modelEnglishName');
        const modelKoreanName = document.getElementById('modelKoreanName');

        if (!modelCode || !modelMfgSelect || !modelEnglishName || !modelKoreanName) return;

        const data = {
            code: modelCode.value,
            manufacturer_code: modelMfgSelect.value,
            english_name: modelEnglishName.value,
            korean_name: modelKoreanName.value
        };

        fetch('/api/add-model', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showAlert('새 모델이 추가되었습니다.', 'success');
                const modal = document.getElementById('addCategoryModal');
                if (modal && window.bootstrap) {
                    const bsModal = bootstrap.Modal.getInstance(modal);
                    if (bsModal) bsModal.hide();
                }
            } else {
                showAlert('추가 실패: ' + data.message, 'danger');
            }
        })
        .catch(error => {
            showAlert('모델 추가 중 오류가 발생했습니다.', 'danger');
        });
    }

    // 제조사 목록 로드
    function loadManufacturers() {
        fetch('/manufacturers')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                manufacturers = data.data;
                updateManufacturerSelects();
            }
        })
        .catch(error => {
            console.error('제조사 목록 로드 실패:', error);
        });
    }

    // 제조사 셀렉트 박스 업데이트
    function updateManufacturerSelects() {
        const selects = ['manufacturerSelect', 'modelMfgSelect'];

        selects.forEach(function(selectId) {
            const select = document.getElementById(selectId);
            if (!select) return;

            select.innerHTML = '<option value="">제조사를 선택하세요</option>';

            manufacturers.forEach(function(manufacturer) {
                const option = document.createElement('option');
                option.value = manufacturer.code;
                option.textContent = `${manufacturer.korean_name}(${manufacturer.english_name})`;
                select.appendChild(option);
            });
        });
    }

    // 모델 목록 로드
    function loadModels(manufacturerCode, targetSelect) {
        fetch(`/manufacturers/${manufacturerCode}/models`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                targetSelect.innerHTML = '<option value="">모델을 선택하세요</option>';

                data.data.forEach(function(model) {
                    const option = document.createElement('option');
                    option.value = model.code;
                    option.textContent = `${model.korean_name}(${model.english_name})`;
                    targetSelect.appendChild(option);
                });
            }
        })
        .catch(error => {
            console.error('모델 목록 로드 실패:', error);
        });
    }

    // 데이터셋 통계 로드
    function loadDatasetStatistics() {
        fetch('/dataset/statistics')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                const stats = data.data;
                let html = `
                    <div class="row text-center">
                        <div class="col-6">
                            <h4 class="text-primary">${stats.total_files}</h4>
                            <small>파일 수</small>
                        </div>
                        <div class="col-6">
                            <h4 class="text-success">${stats.total_entries}</h4>
                            <small>데이터 수</small>
                        </div>
                    </div>
                `;

                if (stats.files && stats.files.length > 0) {
                    html += '<hr><h6>파일 목록:</h6><ul class="list-unstyled">';
                    stats.files.forEach(function(file) {
                        html += `<li><small>${file.file} (${file.entries}개)</small></li>`;
                    });
                    html += '</ul>';
                }

                const datasetStats = document.getElementById('datasetStats');
                if (datasetStats) {
                    datasetStats.innerHTML = html;
                }
            }
        })
        .catch(error => {
            const datasetStats = document.getElementById('datasetStats');
            if (datasetStats) {
                datasetStats.innerHTML = '<p class="text-muted">통계를 불러올 수 없습니다.</p>';
            }
        });
    }

    // 알림 표시
    function showAlert(message, type) {
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show`;
        alert.setAttribute('role', 'alert');
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.body.insertBefore(alert, document.body.firstChild);

        // 3초 후 자동 제거
        setTimeout(function() {
            alert.style.opacity = '0';
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.parentNode.removeChild(alert);
                }
            }, 300);
        }, 3000);
    }

    // 전역 함수로 노출
    window.showManualInputModal = showManualInputModal;
});
