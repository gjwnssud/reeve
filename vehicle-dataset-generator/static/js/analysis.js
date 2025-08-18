document.addEventListener('DOMContentLoaded', function() {
    let analysisResults = [];
    let currentDetailResult = null;

    // 페이지 로드시 분석 결과 로드
    loadAnalysisResults();

    // 주기적으로 분석 진행 상황 업데이트 (10초마다)
    setInterval(updateAnalysisProgress, 10000);

    // 데이터셋 저장 버튼 이벤트
    const saveToDatasetBtn = document.getElementById('saveToDatasetBtn');
    if (saveToDatasetBtn) {
        saveToDatasetBtn.addEventListener('click', function() {
            if (currentDetailResult) {
                saveToDataset(currentDetailResult);
            }
        });
    }

    // 이벤트 위임을 사용한 버튼 이벤트
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('detail-btn') || e.target.closest('.detail-btn')) {
            const btn = e.target.classList.contains('detail-btn') ? e.target : e.target.closest('.detail-btn');
            const index = btn.dataset.index;
            showAnalysisDetail(analysisResults[index]);
        }

        if (e.target.classList.contains('save-btn') || e.target.closest('.save-btn')) {
            const btn = e.target.classList.contains('save-btn') ? e.target : e.target.closest('.save-btn');
            const index = btn.dataset.index;
            saveToDataset(analysisResults[index]);
        }

        if (e.target.classList.contains('retry-btn') || e.target.closest('.retry-btn')) {
            const btn = e.target.classList.contains('retry-btn') ? e.target : e.target.closest('.retry-btn');
            const index = btn.dataset.index;
            retryAnalysis(analysisResults[index]);
        }
    });

    // 분석 결과 로드
    function loadAnalysisResults() {
        // 실제 구현에서는 서버에서 분석 결과를 가져와야 함
        // 여기서는 localStorage를 사용한 임시 구현
        const storedResults = localStorage.getItem('analysisResults');
        if (storedResults) {
            analysisResults = JSON.parse(storedResults);
            displayAnalysisResults();
        }
    }

    // 분석 결과 표시
    function displayAnalysisResults() {
        const tbody = document.getElementById('analysisResultsBody');
        if (!tbody) return;

        tbody.innerHTML = '';

        if (analysisResults.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center text-muted">분석 결과가 없습니다.</td>
                </tr>
            `;
            return;
        }

        analysisResults.forEach(function(result, index) {
            const row = createResultRow(result, index);
            tbody.appendChild(row);
        });
    }

    // 분석 결과 행 생성
    function createResultRow(result, index) {
        const imageName = result.image_path ? result.image_path.split('/').pop() : 'Unknown';
        const statusBadge = getStatusBadge(result.status);
        const confidenceBadge = getConfidenceBadge(result);

        const tr = document.createElement('tr');
        tr.dataset.index = index;
        tr.innerHTML = `
            <td>
                <img src="${result.image_path}" class="img-thumbnail" style="width: 60px; height: 60px; object-fit: cover;">
                <br><small>${imageName}</small>
            </td>
            <td>
                ${result.manufacturer_korean_name || '미분석'}
                <br><small class="text-muted">${result.manufacturer_english_name || ''}</small>
            </td>
            <td>
                ${result.model_korean_name || '미분석'}
                <br><small class="text-muted">${result.model_english_name || ''}</small>
            </td>
            <td>${confidenceBadge}</td>
            <td>${statusBadge}</td>
            <td>
                <div class="btn-group" role="group">
                    <button type="button" class="btn btn-sm btn-info detail-btn" data-index="${index}">
                        <i class="bi bi-eye"></i> 상세
                    </button>
                    ${result.status === 'success' ? `
                        <button type="button" class="btn btn-sm btn-success save-btn" data-index="${index}">
                            <i class="bi bi-save"></i> 저장
                        </button>
                    ` : `
                        <button type="button" class="btn btn-sm btn-warning retry-btn" data-index="${index}">
                            <i class="bi bi-arrow-clockwise"></i> 재분석
                        </button>
                    `}
                </div>
            </td>
        `;

        return tr;
    }

    // 상태 배지 생성
    function getStatusBadge(status) {
        const badges = {
            'success': '<span class="badge bg-success">완료</span>',
            'processing': '<span class="badge bg-primary">분석중</span>',
            'partial': '<span class="badge bg-warning">부분완료</span>',
            'error': '<span class="badge bg-danger">실패</span>',
            'pending': '<span class="badge bg-secondary">대기중</span>'
        };
        return badges[status] || '<span class="badge bg-secondary">알 수 없음</span>';
    }

    // 신뢰도 배지 생성
    function getConfidenceBadge(result) {
        if (result.status !== 'success') {
            return '<span class="text-muted">-</span>';
        }

        const mfgConf = result.manufacturer_confidence || 0;
        const modelConf = result.model_confidence || 0;
        const avgConf = (mfgConf + modelConf) / 2;

        let badgeClass = 'bg-secondary';
        if (avgConf >= 0.8) badgeClass = 'bg-success';
        else if (avgConf >= 0.6) badgeClass = 'bg-warning';
        else badgeClass = 'bg-danger';

        return `<span class="badge ${badgeClass}">${(avgConf * 100).toFixed(1)}%</span>`;
    }

    // 분석 상세 모달 표시
    function showAnalysisDetail(result) {
        currentDetailResult = result;
        
        const imageName = result.image_path ? result.image_path.split('/').pop() : 'Unknown';
        
        let detailHtml = `
            <div class="row">
                <div class="col-md-6">
                    <img src="${result.image_path}" class="img-fluid mb-3" alt="${imageName}">
                    <h6>파일 정보</h6>
                    <ul class="list-unstyled">
                        <li><strong>파일명:</strong> ${imageName}</li>
                        <li><strong>경로:</strong> <small>${result.image_path}</small></li>
                        <li><strong>상태:</strong> ${getStatusBadge(result.status)}</li>
                    </ul>
                </div>
                <div class="col-md-6">
                    <h6>분석 결과</h6>
        `;

        if (result.status === 'success') {
            detailHtml += `
                <div class="card mb-3">
                    <div class="card-body">
                        <h6 class="card-title">제조사</h6>
                        <p class="card-text">
                            <strong>한글명:</strong> ${result.manufacturer_korean_name}<br>
                            <strong>영문명:</strong> ${result.manufacturer_english_name}<br>
                            <strong>코드:</strong> ${result.manufacturer_code}<br>
                            <strong>신뢰도:</strong> 
                            <span class="badge bg-${result.manufacturer_confidence >= 0.8 ? 'success' : result.manufacturer_confidence >= 0.6 ? 'warning' : 'danger'}">
                                ${(result.manufacturer_confidence * 100).toFixed(1)}%
                            </span>
                        </p>
                    </div>
                </div>
                <div class="card mb-3">
                    <div class="card-body">
                        <h6 class="card-title">모델</h6>
                        <p class="card-text">
                            <strong>한글명:</strong> ${result.model_korean_name}<br>
                            <strong>영문명:</strong> ${result.model_english_name}<br>
                            <strong>코드:</strong> ${result.model_code}<br>
                            <strong>신뢰도:</strong> 
                            <span class="badge bg-${result.model_confidence >= 0.8 ? 'success' : result.model_confidence >= 0.6 ? 'warning' : 'danger'}">
                                ${(result.model_confidence * 100).toFixed(1)}%
                            </span>
                        </p>
                    </div>
                </div>
            `;
        } else {
            detailHtml += `
                <div class="alert alert-warning">
                    <h6>분석 실패</h6>
                    <p>${result.message || '분석 중 오류가 발생했습니다.'}</p>
                </div>
            `;
        }

        if (result.bbox) {
            detailHtml += `
                <h6>바운딩 박스</h6>
                <p><small>[${result.bbox.join(', ')}]</small></p>
            `;
        }

        detailHtml += `
                </div>
            </div>
        `;

        const detailBody = document.getElementById('analysisDetailBody');
        if (detailBody) {
            detailBody.innerHTML = detailHtml;
        }
        
        // 저장 버튼 표시/숨김
        const saveBtn = document.getElementById('saveToDatasetBtn');
        if (saveBtn) {
            if (result.status === 'success') {
                saveBtn.style.display = 'block';
            } else {
                saveBtn.style.display = 'none';
            }
        }

        // Bootstrap 모달 표시
        const modal = document.getElementById('analysisDetailModal');
        if (modal && window.bootstrap) {
            const bsModal = new bootstrap.Modal(modal);
            bsModal.show();
        }
    }

    // 데이터셋에 저장
    function saveToDataset(result) {
        const button = document.getElementById('saveToDatasetBtn');
        if (!button) return;

        button.disabled = true;
        button.innerHTML = '<i class="bi bi-hourglass-split"></i> 저장중...';

        fetch('/api/save-dataset', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                file_path: result.image_path,
                manufacturer_code: result.manufacturer_code,
                model_code: result.model_code,
                manufacturer_confidence: result.manufacturer_confidence,
                model_confidence: result.model_confidence,
                bbox: result.bbox
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showAlert('데이터셋에 저장되었습니다.', 'success');
                button.classList.remove('btn-primary');
                button.classList.add('btn-success');
                button.innerHTML = '<i class="bi bi-check"></i> 저장완료';
                
                // 결과 상태 업데이트
                result.saved = true;
                updateAnalysisResults();
                
                setTimeout(function() {
                    const modal = document.getElementById('analysisDetailModal');
                    if (modal && window.bootstrap) {
                        const bsModal = bootstrap.Modal.getInstance(modal);
                        if (bsModal) bsModal.hide();
                    }
                }, 1000);
            } else {
                showAlert('저장 실패: ' + data.message, 'danger');
                button.disabled = false;
                button.innerHTML = '<i class="bi bi-save"></i> 데이터셋에 저장';
            }
        })
        .catch(error => {
            showAlert('저장 중 오류가 발생했습니다.', 'danger');
            button.disabled = false;
            button.innerHTML = '<i class="bi bi-save"></i> 데이터셋에 저장';
        });
    }

    // 재분석
    function retryAnalysis(result) {
        showAlert('재분석을 시작합니다.', 'info');
        
        fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                file_path: result.image_path,
                bbox: result.bbox
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'processing') {
                result.status = 'processing';
                updateAnalysisResults();
                showAlert('재분석이 시작되었습니다.', 'info');
            } else {
                showAlert('재분석 시작 실패: ' + data.message, 'danger');
            }
        })
        .catch(error => {
            showAlert('재분석 중 오류가 발생했습니다.', 'danger');
        });
    }

    // 분석 진행 상황 업데이트
    function updateAnalysisProgress() {
        const processingResults = analysisResults.filter(r => r.status === 'processing');
        const progressContainer = document.getElementById('analysisProgress');
        if (!progressContainer) return;
        
        if (processingResults.length === 0) {
            progressContainer.innerHTML = '<p class="text-muted">분석 중인 이미지가 없습니다.</p>';
            return;
        }

        let progressHtml = '<h6>분석 진행 중:</h6>';
        processingResults.forEach(function(result) {
            const imageName = result.image_path ? result.image_path.split('/').pop() : 'Unknown';
            progressHtml += `
                <div class="alert alert-info alert-sm">
                    <div class="d-flex align-items-center">
                        <img src="${result.image_path}" class="img-thumbnail me-2" style="width: 40px; height: 40px;">
                        <div class="flex-grow-1">
                            <strong>${imageName}</strong>
                            <br><small>분석 진행 중...</small>
                        </div>
                        <div class="spinner-border spinner-border-sm text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                    </div>
                </div>
            `;
        });

        progressContainer.innerHTML = progressHtml;
    }

    // 분석 결과 업데이트
    function updateAnalysisResults() {
        localStorage.setItem('analysisResults', JSON.stringify(analysisResults));
        displayAnalysisResults();
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

    // 샘플 데이터 추가 (개발용)
    function addSampleData() {
        if (analysisResults.length === 0) {
            analysisResults = [
                {
                    image_path: '/temp/sample1.jpg',
                    status: 'success',
                    manufacturer_code: 'hyundai',
                    manufacturer_english_name: 'Hyundai',
                    manufacturer_korean_name: '현대',
                    manufacturer_confidence: 0.95,
                    model_code: 'sonata',
                    model_english_name: 'Sonata',
                    model_korean_name: '쏘나타',
                    model_confidence: 0.88,
                    bbox: [100, 50, 400, 300],
                    saved: false
                },
                {
                    image_path: '/temp/sample2.jpg',
                    status: 'processing',
                    message: '분석 진행 중...'
                },
                {
                    image_path: '/temp/sample3.jpg',
                    status: 'error',
                    message: '제조사를 식별할 수 없습니다.'
                }
            ];
            updateAnalysisResults();
        }
    }

    // 개발용 샘플 데이터 추가
    addSampleData();
});
