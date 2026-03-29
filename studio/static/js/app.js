/**
 * Reeve - 기초 DB 관리 시스템
 * Vanilla JavaScript 프론트엔드
 */

const API_BASE = '';  // Same origin

// 상태 관리
const state = {
    manufacturers: [],
    models: [],
    currentManufacturerId: null,
    currentModelId: null,
    // 리뷰 큐 인피니티 스크롤 상태
    reviewSkip: 0,
    reviewLimit: 20,
    reviewHasMore: true,
    reviewLoading: false,
    reviewTotal: 0
};

// DOM이 로드되면 초기화
document.addEventListener('DOMContentLoaded', () => {
    // 기초데이터 관리 페이지 (basic_data.html)
    if (document.getElementById('manufacturersTable')) {
        initTabs();
        initModals();
        loadManufacturers();

        document.getElementById('addManufacturerBtn').addEventListener('click', () => openManufacturerModal());
        document.getElementById('addModelBtn').addEventListener('click', () => openModelModal());
        document.getElementById('manufacturerForm').addEventListener('submit', handleManufacturerSubmit);
        document.getElementById('modelForm').addEventListener('submit', handleModelSubmit);

        document.querySelectorAll('input[name="domesticFilter"]').forEach(radio => {
            radio.addEventListener('change', filterManufacturers);
        });
        document.getElementById('manufacturerFilter').addEventListener('change', filterModels);
    }

    // 차량데이터 관리 페이지 (index.html / /admin-ui)
    if (document.getElementById('vehicleTableBody')) {
        initVehicleManagement();
    }
});

// 탭 전환 (Bootstrap shown.bs.tab 이벤트로 데이터 로드)
function initTabs() {
    const dataLoaders = {
        manufacturers: loadManufacturers,
        models: loadModels,
        review: loadReviewQueue,
    };
    document.querySelectorAll('[data-bs-toggle="tab"][data-tab]').forEach(btn => {
        btn.addEventListener('shown.bs.tab', () => {
            const loader = dataLoaders[btn.dataset.tab];
            if (loader) loader();
        });
    });
}

// 모달 초기화 (Bootstrap Modal API 사용)
function initModals() {
    const modals = document.querySelectorAll('.modal');

    modals.forEach(modal => {
        // Bootstrap Modal 인스턴스 생성 (backdrop + keyboard close 자동 처리)
        bootstrap.Modal.getOrCreateInstance(modal);
    });
}

// API 호출 헬퍼
async function apiCall(url, options = {}) {
    try {
        const response = await fetch(API_BASE + url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'API 호출 실패');
        }

        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        alert('오류: ' + error.message);
        throw error;
    }
}

// 제조사 목록 로드
async function loadManufacturers() {
    try {
        const data = await apiCall('/admin/manufacturers?limit=1000');
        state.manufacturers = data;
        renderManufacturers(data);
        updateManufacturerSelects(data);
    } catch (error) {
        document.getElementById('manufacturersTableBody').innerHTML =
            '<tr><td colspan="6" class="error">데이터 로드 실패</td></tr>';
    }
}

// 제조사 테이블 렌더링
function renderManufacturers(manufacturers) {
    const tbody = document.getElementById('manufacturersTableBody');

    if (manufacturers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">등록된 제조사가 없습니다</td></tr>';
        return;
    }

    tbody.innerHTML = manufacturers.map(mf => `
        <tr>
            <td>${mf.id}</td>
            <td>${mf.code}</td>
            <td>${mf.english_name}</td>
            <td>${mf.korean_name}</td>
            <td>${mf.is_domestic ? '국내' : '해외'}</td>
            <td>${new Date(mf.created_at).toLocaleDateString('ko-KR')}</td>
        </tr>
    `).join('');
}

// 제조사 필터링
function filterManufacturers() {
    const filter = document.querySelector('input[name="domesticFilter"]:checked').value;
    let filtered = state.manufacturers;

    if (filter === 'domestic') {
        filtered = state.manufacturers.filter(mf => mf.is_domestic === true);
    } else if (filter === 'foreign') {
        filtered = state.manufacturers.filter(mf => mf.is_domestic === false);
    }

    renderManufacturers(filtered);
}

// 제조사 선택 박스 업데이트
function updateManufacturerSelects(manufacturers) {
    const selects = [
        document.getElementById('modelManufacturer'),
        document.getElementById('manufacturerFilter')
    ].filter(Boolean);

    selects.forEach(select => {
        const currentValue = select.value;
        const options = manufacturers.map(mf =>
            `<option value="${mf.id}" data-code="${mf.code}">${mf.korean_name} (${mf.code})</option>`
        ).join('');

        if (select.id === 'manufacturerFilter') {
            select.innerHTML = '<option value="">전체 제조사</option>' + options;
        } else {
            select.innerHTML = '<option value="">제조사 선택</option>' + options;
        }

        select.value = currentValue;
    });
}

// 제조사 모달 열기
function openManufacturerModal(manufacturerId = null) {
    const modal = document.getElementById('manufacturerModal');
    const form = document.getElementById('manufacturerForm');

    form.reset();
    state.currentManufacturerId = manufacturerId;

    modal.querySelector('.modal-title').textContent = manufacturerId ? '제조사 수정' : '제조사 추가';
    bootstrap.Modal.getOrCreateInstance(modal).show();
}

// 제조사 폼 제출
async function handleManufacturerSubmit(e) {
    e.preventDefault();

    const data = {
        code: document.getElementById('mfCode').value,
        english_name: document.getElementById('mfEnglishName').value,
        korean_name: document.getElementById('mfKoreanName').value,
        is_domestic: document.getElementById('mfIsDomestic').checked
    };

    try {
        await apiCall('/admin/manufacturers', {
            method: 'POST',
            body: JSON.stringify(data)
        });

        alert('제조사가 추가되었습니다');
        bootstrap.Modal.getInstance(document.getElementById('manufacturerModal')).hide();
        loadManufacturers();
    } catch (error) {
        // 에러는 apiCall에서 처리됨
    }
}

// 차량 모델 목록 로드
async function loadModels() {
    try {
        const data = await apiCall('/admin/vehicle-models?limit=1000');
        state.models = data;
        renderModels(data);
    } catch (error) {
        document.getElementById('modelsTableBody').innerHTML =
            '<tr><td colspan="6" class="error">데이터 로드 실패</td></tr>';
    }
}

// 차량 모델 테이블 렌더링
function renderModels(models) {
    const tbody = document.getElementById('modelsTableBody');

    if (models.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">등록된 모델이 없습니다</td></tr>';
        return;
    }

    tbody.innerHTML = models.map(model => {
        const manufacturer = state.manufacturers.find(mf => mf.id === model.manufacturer_id);
        const manufacturerName = manufacturer ? manufacturer.korean_name : model.manufacturer_code;

        return `
            <tr>
                <td>${model.id}</td>
                <td>${model.code}</td>
                <td>${manufacturerName}</td>
                <td>${model.english_name}</td>
                <td>${model.korean_name}</td>
                <td>${new Date(model.created_at).toLocaleDateString('ko-KR')}</td>
            </tr>
        `;
    }).join('');
}

// 모델 필터링
function filterModels() {
    const manufacturerId = document.getElementById('manufacturerFilter').value;
    let filtered = state.models;

    if (manufacturerId) {
        filtered = state.models.filter(model => model.manufacturer_id === parseInt(manufacturerId));
    }

    renderModels(filtered);
}

// 차량 모델 모달 열기
function openModelModal(modelId = null) {
    const modal = document.getElementById('modelModal');
    const form = document.getElementById('modelForm');

    form.reset();
    state.currentModelId = modelId;

    // 제조사 목록 로드 확인
    if (state.manufacturers.length === 0) {
        loadManufacturers();
    }

    modal.querySelector('.modal-title').textContent = modelId ? '모델 수정' : '모델 추가';
    bootstrap.Modal.getOrCreateInstance(modal).show();
}

// 차량 모델 폼 제출
async function handleModelSubmit(e) {
    e.preventDefault();

    const manufacturerSelect = document.getElementById('modelManufacturer');
    const selectedOption = manufacturerSelect.options[manufacturerSelect.selectedIndex];

    const data = {
        code: document.getElementById('modelCode').value,
        manufacturer_id: parseInt(manufacturerSelect.value),
        manufacturer_code: selectedOption.dataset.code,
        english_name: document.getElementById('modelEnglishName').value,
        korean_name: document.getElementById('modelKoreanName').value
    };

    try {
        await apiCall('/admin/vehicle-models', {
            method: 'POST',
            body: JSON.stringify(data)
        });

        alert('차량 모델이 추가되었습니다');
        bootstrap.Modal.getInstance(document.getElementById('modelModal')).hide();
        loadModels();
    } catch (error) {
        // 에러는 apiCall에서 처리됨
    }
}

// =====================================================
// 벡터DB 저장 관리 (검수 대기 목록)
// =====================================================

// 검수 대기 목록 로드 (인피니티 스크롤 지원)
async function loadReviewQueue(append = false) {
    const container = document.getElementById('reviewContainer');
    const loader = document.getElementById('infiniteScrollLoader');

    if (!append) {
        state.reviewSkip = 0;
        state.reviewHasMore = true;
        container.innerHTML = '<p class="loading">데이터를 불러오는 중...</p>';
    }

    if (state.reviewLoading || !state.reviewHasMore) return;
    state.reviewLoading = true;
    if (append) loader.style.display = 'block';

    try {
        const data = await apiCall(`/admin/review-queue?skip=${state.reviewSkip}&limit=${state.reviewLimit}`);
        state.reviewTotal = data.total;
        state.reviewHasMore = data.has_more;
        state.reviewSkip += data.items.length;

        if (!append) {
            if (data.items.length === 0) {
                container.innerHTML = '<p class="empty">검수 대기 중인 항목이 없습니다</p>';
            } else {
                container.innerHTML = '';
                renderReviewItems(container, data.items);
            }
        } else {
            renderReviewItems(container, data.items);
        }
    } catch (error) {
        if (!append) container.innerHTML = '<p class="error">데이터 로드 실패</p>';
    } finally {
        state.reviewLoading = false;
        loader.style.display = 'none';
    }
}

// 검수 아이템 렌더링
function renderReviewItems(container, items) {
    items.forEach(item => {
        const div = document.createElement('div');
        div.className = 'review-item';
        div.dataset.id = item.id;
        div.innerHTML = `
            <div class="review-info">
                <img src="/${item.image_path}" alt="차량 이미지" class="review-image" style="cursor:pointer;" onclick="openImageDetail(${item.id}, '${item.image_path}', '${(item.manufacturer || 'N/A').replace(/'/g, "\\'")}', '${(item.model || 'N/A').replace(/'/g, "\\'")}', ${item.matched_manufacturer_id || 'null'}, ${item.matched_model_id || 'null'})" onerror="this.onerror=null; this.style.display='none'; this.parentElement.insertAdjacentHTML('afterbegin', '<div class=\\'no-image\\'>이미지 없음</div>');">
                <div class="review-details">
                    <p><strong>ID:</strong> ${item.id}</p>
                    <p><strong>분석 결과:</strong> ${item.manufacturer || 'N/A'} ${item.model || 'N/A'}</p>
                    <p><strong>신뢰도:</strong> ${item.confidence_score ? item.confidence_score.toFixed(1) + '%' : 'N/A'}</p>
                    <p><strong>등록일:</strong> ${new Date(item.created_at).toLocaleString('ko-KR')}</p>
                </div>
            </div>
            <div class="review-actions">
                <button class="btn btn-primary" style="font-size:0.85rem;" onclick="openImageDetail(${item.id}, '${item.image_path}', '${(item.manufacturer || 'N/A').replace(/'/g, "\\'")}', '${(item.model || 'N/A').replace(/'/g, "\\'")}', ${item.matched_manufacturer_id || 'null'}, ${item.matched_model_id || 'null'})">분석결과 수정</button>
                <button class="btn btn-danger" onclick="deleteReview(${item.id})">분석결과 삭제</button>
                <button class="btn btn-success" onclick="saveToVectorDB(${item.id})">벡터DB 저장</button>
            </div>
        `;
        container.appendChild(div);
    });
}

// 인피니티 스크롤 이벤트
(function initInfiniteScroll() {
    window.addEventListener('scroll', () => {
        // 리뷰 탭이 활성화된 경우에만
        const reviewTab = document.getElementById('review');
        if (!reviewTab || !reviewTab.classList.contains('active')) return;

        const scrollBottom = window.innerHeight + window.scrollY;
        const docHeight = document.documentElement.scrollHeight;

        if (scrollBottom >= docHeight - 200 && state.reviewHasMore && !state.reviewLoading) {
            loadReviewQueue(true);
        }
    });
})();

// =====================================================
// 이미지 상세/수정 모달
// =====================================================

function openImageDetail(analyzedId, imagePath, manufacturer, model, mfId, modelId) {
    const modal = document.getElementById('imageDetailModal');
    document.getElementById('detailImage').src = '/' + imagePath;
    document.getElementById('editAnalyzedId').value = analyzedId;
    document.getElementById('imageDetailTitle').textContent = `차량 이미지 #${analyzedId}`;
    document.getElementById('currentAnalysis').textContent = `${manufacturer} ${model}`;

    // 제조사 셀렉트 업데이트
    const mfSelect = document.getElementById('editManufacturer');
    mfSelect.innerHTML = '<option value="">제조사 선택</option>' +
        state.manufacturers.map(mf =>
            `<option value="${mf.id}" data-code="${mf.code}">${mf.korean_name} (${mf.code})</option>`
        ).join('');

    if (mfId) mfSelect.value = mfId;

    // 모델 셀렉트 업데이트
    loadModelsForManufacturer(mfId, modelId);

    // 인라인 추가 영역 초기화
    closeInlineAddManufacturer();
    closeInlineAddModel();

    bootstrap.Modal.getOrCreateInstance(modal).show();
}

// 기초데이터 관리 모달: 제조사 변경시 모델 목록 업데이트
document.addEventListener('DOMContentLoaded', () => {
    const mfSelect = document.getElementById('editManufacturer');
    if (mfSelect) {
        mfSelect.addEventListener('change', () => {
            const mfId = mfSelect.value ? parseInt(mfSelect.value) : null;
            loadModelsForManufacturer(mfId, null);
        });
    }
    // 차량데이터 관리 모달: 제조사 변경시 모델 목록 업데이트
    const vehicleMfSelect = document.getElementById('vehicleEditManufacturer');
    if (vehicleMfSelect) {
        vehicleMfSelect.addEventListener('change', () => {
            const mfId = vehicleMfSelect.value ? parseInt(vehicleMfSelect.value) : null;
            loadVehicleEditModels(mfId, null);
        });
    }
});

async function loadModelsForManufacturer(manufacturerId, selectedModelId) {
    const modelSelect = document.getElementById('editModel');

    if (!manufacturerId) {
        modelSelect.innerHTML = '<option value="">제조사를 먼저 선택하세요</option>';
        return;
    }

    try {
        const models = await apiCall(`/admin/vehicle-models?manufacturer_id=${manufacturerId}&limit=1000`);
        modelSelect.innerHTML = '<option value="">모델 선택</option>' +
            models.map(m =>
                `<option value="${m.id}">${m.korean_name} (${m.code})</option>`
            ).join('');

        if (selectedModelId) modelSelect.value = selectedModelId;
    } catch (error) {
        modelSelect.innerHTML = '<option value="">모델 로드 실패</option>';
    }
}

// 수정 저장
async function saveEditedAnalysis() {
    const analyzedId = document.getElementById('editAnalyzedId').value;
    const mfSelect = document.getElementById('editManufacturer');
    const modelSelect = document.getElementById('editModel');

    if (!mfSelect.value || !modelSelect.value) {
        alert('제조사와 모델을 모두 선택해주세요.');
        return;
    }

    const mfOption = mfSelect.options[mfSelect.selectedIndex];
    const modelOption = modelSelect.options[modelSelect.selectedIndex];

    const newManufacturer = mfOption.textContent.split(' (')[0];
    const newModel = modelOption.textContent.split(' (')[0];
    const newMfId = parseInt(mfSelect.value);
    const newModelId = parseInt(modelSelect.value);

    try {
        await apiCall(`/admin/review/${analyzedId}`, {
            method: 'PATCH',
            body: JSON.stringify({
                matched_manufacturer_id: newMfId,
                matched_model_id: newModelId,
                manufacturer: newManufacturer,
                model: newModel
            })
        });

        bootstrap.Modal.getInstance(document.getElementById('imageDetailModal')).hide();

        // 리로딩 없이 해당 아이템의 UI만 업데이트
        const itemEl = document.querySelector(`.review-item[data-id="${analyzedId}"]`);
        if (itemEl) {
            const detailsEl = itemEl.querySelector('.review-details');
            if (detailsEl) {
                const analysisP = detailsEl.querySelector('p:nth-child(2)');
                if (analysisP) {
                    analysisP.innerHTML = `<strong>분석 결과:</strong> ${newManufacturer} ${newModel}`;
                }
            }
            // 버튼의 onclick에 새로운 값 반영
            const imagePath = itemEl.querySelector('.review-image')?.src?.replace(window.location.origin + '/', '') || '';
            const editBtns = itemEl.querySelectorAll('.btn-primary');
            const imgEl = itemEl.querySelector('.review-image');
            const escapedMf = newManufacturer.replace(/'/g, "\\'");
            const escapedModel = newModel.replace(/'/g, "\\'");
            const onclickStr = `openImageDetail(${analyzedId}, '${imagePath}', '${escapedMf}', '${escapedModel}', ${newMfId}, ${newModelId})`;
            editBtns.forEach(btn => btn.setAttribute('onclick', onclickStr));
            if (imgEl) imgEl.setAttribute('onclick', onclickStr);
        }

        alert('수정되었습니다.');
    } catch (error) {
        // apiCall에서 에러 처리됨
    }
}

// =====================================================
// 인라인 제조사/모델 추가
// =====================================================

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
        const newMf = await apiCall('/admin/manufacturers', {
            method: 'POST',
            body: JSON.stringify({
                code, english_name: english, korean_name: korean, is_domestic: isDomestic
            })
        });

        // 전역 상태 업데이트
        state.manufacturers.push(newMf);
        updateManufacturerSelects(state.manufacturers);

        // 모달 내 셀렉트도 업데이트
        const mfSelect = document.getElementById('editManufacturer');
        mfSelect.innerHTML = '<option value="">제조사 선택</option>' +
            state.manufacturers.map(mf =>
                `<option value="${mf.id}" data-code="${mf.code}">${mf.korean_name} (${mf.code})</option>`
            ).join('');
        mfSelect.value = newMf.id;

        // 해당 제조사의 모델 목록 로드
        loadModelsForManufacturer(newMf.id, null);

        closeInlineAddManufacturer();
        alert(`제조사 "${korean}" 이 추가되었습니다.`);
    } catch (error) {
        // apiCall에서 에러 처리됨
    }
}

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
        const newModel = await apiCall('/admin/vehicle-models', {
            method: 'POST',
            body: JSON.stringify({
                code, manufacturer_id: mfId, manufacturer_code: mfCode,
                english_name: english, korean_name: korean
            })
        });

        // 모델 셀렉트 리로드 후 새 모델 선택
        await loadModelsForManufacturer(mfId, newModel.id);

        closeInlineAddModel();
        alert(`모델 "${korean}" 이 추가되었습니다.`);
    } catch (error) {
        // apiCall에서 에러 처리됨
    }
}

// 벡터DB에 저장
async function saveToVectorDB(id) {
    if (!confirm('이 데이터를 벡터DB에 저장하시겠습니까?')) {
        return;
    }

    try {
        await apiCall(`/admin/review/${id}`, {
            method: 'POST',
            body: JSON.stringify({
                approved: true
            })
        });

        // 리로딩 없이 해당 아이템만 DOM에서 제거
        const itemEl = document.querySelector(`.review-item[data-id="${id}"]`);
        if (itemEl) {
            itemEl.style.transition = 'opacity 0.3s';
            itemEl.style.opacity = '0';
            setTimeout(() => itemEl.remove(), 300);
        }
        state.reviewSkip = Math.max(0, state.reviewSkip - 1);
        state.reviewTotal = Math.max(0, state.reviewTotal - 1);

        alert('벡터DB에 저장되었습니다');
    } catch (error) {
        // 에러는 apiCall에서 처리됨
    }
}

// 데이터 삭제
async function deleteReview(id) {
    if (!confirm('이 데이터를 삭제하시겠습니까?\n삭제된 데이터는 복구할 수 없습니다.')) {
        return;
    }

    try {
        await apiCall(`/admin/review/${id}`, {
            method: 'DELETE'
        });

        // 리로딩 없이 해당 아이템만 DOM에서 제거
        const itemEl = document.querySelector(`.review-item[data-id="${id}"]`);
        if (itemEl) {
            itemEl.style.transition = 'opacity 0.3s';
            itemEl.style.opacity = '0';
            setTimeout(() => itemEl.remove(), 300);
        }
        state.reviewSkip = Math.max(0, state.reviewSkip - 1);
        state.reviewTotal = Math.max(0, state.reviewTotal - 1);

        alert('삭제되었습니다');
    } catch (error) {
        // 에러는 apiCall에서 처리됨
    }
}

// 일괄 벡터DB 저장 시작 (DB 전체 대상 - is_verified=false)
async function startBatchAnalysis() {
    if (!confirm('검수 대기 중인 전체 데이터를 벡터DB에 일괄 저장하시겠습니까?\n(제조사와 모델이 식별된 항목만 저장됩니다)\n\n저장 후에는 검색 시스템에서 사용됩니다.')) {
        return;
    }

    const progressContainer = document.getElementById('batchProgressContainer');
    const progressBar = document.getElementById('batchProgressBar');
    const progressText = document.getElementById('batchProgressText');
    const analyzeBtn = document.getElementById('analyzeAllBtn');
    const deleteBtn = document.getElementById('deleteAllBtn');

    progressContainer.style.display = 'block';
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = '저장 중...';
    deleteBtn.disabled = true;

    progressBar.style.width = '0%';
    progressBar.textContent = '0%';
    progressText.textContent = '서버에서 전체 데이터를 처리 중...';

    try {
        const response = await fetch('/admin/review/batch-save-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalResult = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const jsonStr = line.slice(6).trim();
                if (!jsonStr) continue;

                try {
                    const event = JSON.parse(jsonStr);

                    if (event.type === 'start') {
                        if (event.total === 0) {
                            progressText.textContent = '저장할 수 있는 데이터가 없습니다. (제조사/모델이 식별된 항목 없음)';
                        } else {
                            let startMsg = `전체 ${event.total}개 항목 처리 시작...`;
                            if (event.skipped > 0) startMsg += ` (제조사/모델 미식별 ${event.skipped}개 제외)`;
                            progressText.textContent = startMsg;
                        }
                    } else if (event.type === 'progress') {
                        const progress = Math.round((event.current / event.total) * 100);
                        progressBar.style.width = `${progress}%`;
                        progressBar.textContent = `${progress}%`;
                        progressText.textContent = `진행: ${event.current}/${event.total} (✅ 성공: ${event.succeeded}, ❌ 실패: ${event.failed})`;

                        const itemEl = document.querySelector(`.review-item[data-id="${event.item_id}"]`);
                        if (itemEl && event.succeeded === event.current - event.failed) {
                            itemEl.style.transition = 'opacity 0.3s';
                            itemEl.style.opacity = '0';
                            setTimeout(() => itemEl.remove(), 300);
                        }
                    } else if (event.type === 'done') {
                        finalResult = event;
                    }
                } catch (e) {
                    console.error('SSE parse error:', e);
                }
            }
        }

        if (finalResult) {
            progressText.textContent = `✨ 완료! 총 ${finalResult.total}개 중 ${finalResult.succeeded}개 저장 완료, ${finalResult.failed}개 실패`;
            alert(`벡터DB 일괄 저장이 완료되었습니다.\n\n✅ 저장 완료: ${finalResult.succeeded}개\n❌ 실패: ${finalResult.failed}개`);
        } else {
            progressText.textContent = '저장할 수 있는 데이터가 없습니다.';
        }

    } catch (error) {
        console.error('Batch save error:', error);
        progressText.textContent = `❌ 오류 발생: ${error.message}`;
        alert('일괄 저장 중 오류가 발생했습니다.');
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = '💾 전체 일괄 벡터DB 저장';
        deleteBtn.disabled = false;

        setTimeout(() => {
            progressContainer.style.display = 'none';
            progressBar.style.width = '0%';
            progressBar.textContent = '';
            state.reviewSkip = 0;
            state.reviewHasMore = true;
            loadReviewQueue();
        }, 3000);
    }
}

// 일괄 삭제 (DB 레벨 전체 삭제 - 이미지 파일 + MySQL 데이터 포함)
async function startBatchDelete() {
    const totalCount = state.reviewTotal;

    if (totalCount === 0) {
        alert('삭제할 데이터가 없습니다.');
        return;
    }

    if (!confirm(`⚠️ 검수 대기 중인 전체 ${totalCount}개 데이터를 삭제하시겠습니까?\n\n` +
        `삭제 범위:\n` +
        `• data/uploads (원본 업로드 이미지)\n` +
        `• data/crops (크롭 이미지)\n` +
        `• MySQL 분석 결과 레코드\n\n` +
        `삭제된 데이터는 복구할 수 없습니다.`)) {
        return;
    }

    const progressContainer = document.getElementById('batchDeleteProgressContainer');
    const progressBar = document.getElementById('batchDeleteProgressBar');
    const progressText = document.getElementById('batchDeleteProgressText');
    const deleteBtn = document.getElementById('deleteAllBtn');
    const analyzeBtn = document.getElementById('analyzeAllBtn');

    progressContainer.style.display = 'block';
    deleteBtn.disabled = true;
    deleteBtn.textContent = '삭제 중...';
    analyzeBtn.disabled = true;

    progressBar.style.width = '50%';
    progressBar.textContent = '처리 중...';
    progressText.textContent = '서버에서 전체 데이터를 삭제 중...';

    try {
        const result = await apiCall('/admin/review-delete-all', {
            method: 'DELETE'
        });

        progressBar.style.width = '100%';
        progressBar.textContent = '100%';
        progressText.textContent = `✨ 완료! ${result.total}개 레코드, ${result.deleted_files}개 파일 삭제 완료`;

        alert(`전체 삭제 완료!\n\n✅ 삭제된 레코드: ${result.total}개\n🗑️ 삭제된 파일: ${result.deleted_files}개`);

    } catch (error) {
        console.error('Batch delete error:', error);
        progressText.textContent = `❌ 오류 발생: ${error.message}`;
        alert('일괄 삭제 중 오류가 발생했습니다.');
    } finally {
        deleteBtn.disabled = false;
        deleteBtn.textContent = '🗑️ 전체 일괄 삭제';
        analyzeBtn.disabled = false;

        setTimeout(() => {
            progressContainer.style.display = 'none';
            progressBar.style.width = '0%';
            progressBar.textContent = '';
            state.reviewSkip = 0;
            state.reviewHasMore = true;
            loadReviewQueue();
        }, 3000);
    }
}


// =====================================================
// 차량데이터 관리 (/admin-ui — index.html)
// =====================================================

const vehicleState = {
    currentPage: 0,
    pageSize: 20,
    status: 'all',
    total: 0,
    manufacturerId: null,
    items: [],
    selectedIds: new Set(),
    editManufacturers: [],
    currentItem: null
};

// BBox 드로잉 상태
const bboxDraw = {
    canvas: null,
    ctx: null,
    img: null,
    dragMode: null,  // 'draw' | 'move' | 'resize-tl' | 'resize-tr' | 'resize-bl' | 'resize-br'
    startPos: null,
    startBbox: null,
    currentBbox: null,   // [x1,y1,x2,y2] 원본 이미지 좌표
    origBbox: null,      // 모달 열 때 기존 bbox (초기화 용)
    yoloDetections: []
};

function initVehicleManagement() {
    loadVehicleData();
    loadVehicleManufacturerFilter();

    // 상태 탭 클릭
    document.querySelectorAll('#vehicleStatusTabs .nav-link').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#vehicleStatusTabs .nav-link').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            vehicleState.status = btn.dataset.status;
            vehicleState.currentPage = 0;
            loadVehicleData();
        });
    });

    // 제조사 필터
    const mfFilter = document.getElementById('mfFilterVehicle');
    if (mfFilter) {
        mfFilter.addEventListener('change', (e) => {
            vehicleState.manufacturerId = e.target.value ? parseInt(e.target.value) : null;
            vehicleState.currentPage = 0;
            loadVehicleData();
        });
    }

    // 전체 선택 체크박스
    const selectAll = document.getElementById('vehicleSelectAll');
    if (selectAll) {
        selectAll.addEventListener('change', (e) => {
            document.querySelectorAll('.vehicle-checkbox').forEach(cb => {
                cb.checked = e.target.checked;
                const id = parseInt(cb.value);
                if (e.target.checked) vehicleState.selectedIds.add(id);
                else vehicleState.selectedIds.delete(id);
            });
        });
    }
}

async function loadVehicleManufacturerFilter() {
    try {
        const resp = await fetch(API_BASE + '/admin/manufacturers?limit=1000');
        if (!resp.ok) return;
        const data = await resp.json();
        vehicleState.editManufacturers = data;
        const select = document.getElementById('mfFilterVehicle');
        if (select) {
            select.innerHTML = '<option value="">전체 제조사</option>' +
                data.map(mf => `<option value="${mf.id}">${mf.korean_name} (${mf.code})</option>`).join('');
        }
    } catch (e) {}
}

async function loadVehicleData() {
    const { currentPage, pageSize, status, manufacturerId } = vehicleState;
    const skip = currentPage * pageSize;

    let url = `/admin/analyzed-vehicles?skip=${skip}&limit=${pageSize}`;
    if (status !== 'all') url += `&status=${status}`;
    if (manufacturerId) url += `&manufacturer_id=${manufacturerId}`;

    const tbody = document.getElementById('vehicleTableBody');
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted"><i class="bi bi-arrow-repeat"></i> 로딩 중...</td></tr>';

    try {
        const resp = await fetch(API_BASE + url);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const { total, items } = await resp.json();
        vehicleState.total = total;
        vehicleState.items = items;

        renderVehicleTable(items);
        renderVehiclePagination(total);
        updateVehicleTabBadges();
    } catch (e) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-danger">오류: ${e.message}</td></tr>`;
    }
}

function getVehicleStatusInfo(item) {
    if (item.is_verified) return { color: 'success', label: '검증완료' };
    const stage = item.processing_stage;
    if (stage === 'analysis_complete' || stage === 'verified') {
        if (item.manufacturer && item.model) return { color: 'info', label: '분석완료' };
        return { color: 'danger', label: '분석실패' };
    }
    if (stage === 'yolo_detected') {
        if (item.yolo_detections && item.yolo_detections.length > 0) return { color: 'primary', label: '감지완료' };
        return { color: 'warning', label: '탐지실패' };
    }
    if (stage === 'uploaded') return { color: 'secondary', label: '업로드' };
    return { color: 'secondary', label: stage || '-' };
}

function renderVehicleTable(items) {
    const tbody = document.getElementById('vehicleTableBody');
    if (!tbody) return;
    vehicleState.selectedIds.clear();
    const selectAll = document.getElementById('vehicleSelectAll');
    if (selectAll) selectAll.checked = false;

    if (!items.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-muted">데이터가 없습니다</td></tr>';
        return;
    }

    tbody.innerHTML = items.map(item => {
        const si = getVehicleStatusInfo(item);
        const imgPath = item.original_image_path || item.image_path;
        const imgSrc = imgPath ? `/${imgPath}` : '';
        const dateStr = item.created_at ? new Date(item.created_at).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Seoul' }) : '-';

        return `<tr id="vehicle-row-${item.id}">
            <td><input type="checkbox" class="vehicle-checkbox form-check-input" value="${item.id}"
                onchange="toggleVehicleSelect(${item.id}, this.checked)"></td>
            <td>${imgSrc ? `<img src="${imgSrc}" style="width:60px;height:42px;object-fit:cover;border-radius:4px;" onerror="this.style.display='none'">` : '<span class="text-muted small">-</span>'}</td>
            <td><span class="badge rounded-pill bg-${si.color}">${si.label}</span></td>
            <td class="small">${item.manufacturer || '<span class="text-muted">-</span>'}</td>
            <td class="small">${item.model || '<span class="text-muted">-</span>'}</td>
            <td class="small text-muted" style="white-space:nowrap;">${dateStr}</td>
            <td>
                <div class="d-flex gap-1">
                    <button class="btn btn-outline-secondary btn-sm py-0 px-1" onclick="openVehicleEditModal(${item.id})" title="편집"><i class="bi bi-pencil"></i></button>
                    <button class="btn btn-outline-danger btn-sm py-0 px-1" onclick="deleteVehicle(${item.id})" title="삭제"><i class="bi bi-trash"></i></button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

function toggleVehicleSelect(id, checked) {
    if (checked) vehicleState.selectedIds.add(id);
    else vehicleState.selectedIds.delete(id);
}

function renderVehiclePagination(total) {
    const { currentPage: cur, pageSize } = vehicleState;
    const navEl = document.getElementById('vehiclePagination');
    if (!navEl) return;

    const totalPages = Math.ceil(total / pageSize);
    if (totalPages <= 1) {
        navEl.innerHTML = `<p class="text-muted small text-center mb-0">총 ${total}개</p>`;
        return;
    }

    const half = 2;
    const start = Math.max(0, Math.min(cur - half, totalPages - 5));
    const end = Math.min(totalPages - 1, start + 4);

    let items = '';
    if (start > 0) items += `<li class="page-item"><button class="page-link" onclick="goToVehiclePage(0)">1</button></li><li class="page-item disabled"><span class="page-link">…</span></li>`;
    for (let i = start; i <= end; i++) {
        items += `<li class="page-item${i === cur ? ' active' : ''}"><button class="page-link" onclick="goToVehiclePage(${i})">${i + 1}</button></li>`;
    }
    if (end < totalPages - 1) items += `<li class="page-item disabled"><span class="page-link">…</span></li><li class="page-item"><button class="page-link" onclick="goToVehiclePage(${totalPages - 1})">${totalPages}</button></li>`;

    navEl.innerHTML = `
        <ul class="pagination justify-content-center flex-wrap mb-1">
            <li class="page-item${cur === 0 ? ' disabled' : ''}"><button class="page-link" onclick="goToVehiclePage(${cur - 1})"><i class="bi bi-chevron-left"></i></button></li>
            ${items}
            <li class="page-item${cur >= totalPages - 1 ? ' disabled' : ''}"><button class="page-link" onclick="goToVehiclePage(${cur + 1})"><i class="bi bi-chevron-right"></i></button></li>
        </ul>
        <p class="text-center text-muted small mb-0">총 ${total}개 / ${cur + 1}/${totalPages} 페이지</p>`;
}

function goToVehiclePage(page) {
    vehicleState.currentPage = page;
    loadVehicleData();
}

async function updateVehicleTabBadges() {
    const statusMap = [
        ['all', 'badgeAll'], ['uploaded', 'badgeUploaded'],
        ['yolo_detected', 'badgeYoloDetected'], ['analysis_complete', 'badgeAnalysisComplete'],
        ['verified', 'badgeVerified']
    ];
    for (const [s, badgeId] of statusMap) {
        try {
            const url = s === 'all' ? '/admin/analyzed-vehicles?limit=1' : `/admin/analyzed-vehicles?limit=1&status=${s}`;
            const resp = await fetch(API_BASE + url);
            if (resp.ok) {
                const { total } = await resp.json();
                const badge = document.getElementById(badgeId);
                if (badge) badge.textContent = total;
            }
        } catch (e) {}
    }
}

function showAdminToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.style.cssText = 'position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;padding:.6rem 1.2rem;border-radius:8px;color:#fff;font-size:.9rem;box-shadow:0 4px 12px rgba(0,0,0,.2);transition:opacity .3s;';
    if (type === 'error') toast.style.background = '#ef4444';
    else if (type === 'success') toast.style.background = '#10b981';
    else toast.style.background = '#6366f1';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 3000);
}

async function openVehicleEditModal(id) {
    const item = vehicleState.items.find(it => it.id === id);
    if (!item) return;
    vehicleState.currentItem = item;

    document.getElementById('vehicleEditId').value = id;
    document.getElementById('vehicleEditTitle').textContent = `차량데이터 편집 #${id}`;
    document.getElementById('vehicleEditCurrentAnalysis').textContent =
        `현재: ${item.manufacturer || 'N/A'} / ${item.model || 'N/A'}`;

    // 재분석 상태 초기화
    const statusEl = document.getElementById('vehicleReanalyzeStatus');
    if (statusEl) { statusEl.style.display = 'none'; statusEl.textContent = ''; }
    const reBtn = document.getElementById('vehicleReanalyzeBtn');
    if (reBtn) { reBtn.disabled = false; reBtn.innerHTML = '<i class="bi bi-bounding-box"></i> 재분석 (선택 영역 기준)'; }
    const quickBtn = document.getElementById('vehicleQuickReanalyzeBtn');
    if (quickBtn) { quickBtn.disabled = false; quickBtn.innerHTML = '<i class="bi bi-arrow-repeat"></i> 재분석 (기존 이미지 그대로)'; }

    if (!vehicleState.editManufacturers.length) {
        await loadVehicleManufacturerFilter();
    }
    const mfSelect = document.getElementById('vehicleEditManufacturer');
    mfSelect.innerHTML = '<option value="">제조사 선택</option>' +
        vehicleState.editManufacturers.map(mf =>
            `<option value="${mf.id}" data-code="${mf.code}">${mf.korean_name} (${mf.code})</option>`
        ).join('');
    if (item.matched_manufacturer_id) mfSelect.value = item.matched_manufacturer_id;

    await loadVehicleEditModels(item.matched_manufacturer_id, item.matched_model_id);
    closeVehicleInlineAddManufacturer();
    closeVehicleInlineAddModel();

    // Canvas 초기화
    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('vehicleEditModal'));
    modal.show();

    const imgSrc = item.original_image_path ? `/${item.original_image_path}` : (item.image_path ? `/${item.image_path}` : '');

    // selected_bbox 없으면 첫 번째 YOLO 감지박스 폴백
    let initBbox = item.selected_bbox || null;
    if (!initBbox && item.yolo_detections && item.yolo_detections.length > 0) {
        const det = item.yolo_detections[0];
        initBbox = Array.isArray(det.bbox) ? det.bbox : (Array.isArray(det) ? det : null);
    }

    initVehicleEditCanvas(imgSrc, initBbox, item.yolo_detections);
}

// ── Canvas BBox 드로잉 ─────────────────────────────────────────

const HANDLE_PX = 8;

function initVehicleEditCanvas(imgSrc, selectedBbox, yoloDetections) {
    const canvas = document.getElementById('vehicleEditCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    bboxDraw.canvas = canvas;
    bboxDraw.ctx = ctx;
    bboxDraw.yoloDetections = yoloDetections || [];
    bboxDraw.dragMode = null;

    // 초기 bbox: selected_bbox → yolo[0] → null 순으로 폴백
    let initBbox = selectedBbox ? [...selectedBbox] : null;
    if (!initBbox && bboxDraw.yoloDetections.length > 0) {
        const d = bboxDraw.yoloDetections[0];
        const b = Array.isArray(d.bbox) ? d.bbox : (Array.isArray(d) ? d : null);
        if (b) initBbox = [...b];
    }
    bboxDraw.currentBbox = initBbox;
    bboxDraw.origBbox = initBbox ? [...initBbox] : null;

    canvas.onmousedown = null; canvas.onmousemove = null;
    canvas.onmouseup = null;   canvas.onmouseleave = null;
    updateVehicleBboxInfo();

    if (!imgSrc) { _canvasMsg(ctx, canvas, '이미지 없음'); return; }

    const img = new Image();
    img.onload = () => {
        bboxDraw.img = img;
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        drawVehicleCanvas();
        canvas.onmousedown  = bboxMouseDown;
        canvas.onmousemove  = bboxMouseMove;
        canvas.onmouseup    = bboxMouseUp;
        canvas.onmouseleave = bboxMouseUp;
    };
    img.onerror = () => _canvasMsg(ctx, canvas, '이미지 로드 실패');
    img.src = imgSrc;
}

function _canvasMsg(ctx, canvas, msg) {
    canvas.width = 400; canvas.height = 300;
    ctx.fillStyle = '#333'; ctx.fillRect(0, 0, 400, 300);
    ctx.fillStyle = '#aaa'; ctx.font = '14px sans-serif';
    ctx.textAlign = 'center'; ctx.fillText(msg, 200, 150);
}

function getCanvasPos(e) {
    const c = bboxDraw.canvas, r = c.getBoundingClientRect();
    return { x: (e.clientX - r.left) * (c.width / r.width),
             y: (e.clientY - r.top)  * (c.height / r.height) };
}

function getHandleSize() {
    const c = bboxDraw.canvas;
    if (!c) return 10;
    const r = c.getBoundingClientRect();
    return HANDLE_PX * (c.width / r.width);
}

// hit 테스트: 우선순위 = 코너핸들 > 선택박스내부 > YOLO박스 > 새그리기
function getBboxHitTarget(pos) {
    const b = bboxDraw.currentBbox;
    const hs = getHandleSize();
    const near = (a, v) => Math.abs(a - v) < hs;

    if (b) {
        const [x1, y1, x2, y2] = b;
        if (near(pos.x, x1) && near(pos.y, y1)) return { type: 'resize-tl' };
        if (near(pos.x, x2) && near(pos.y, y1)) return { type: 'resize-tr' };
        if (near(pos.x, x1) && near(pos.y, y2)) return { type: 'resize-bl' };
        if (near(pos.x, x2) && near(pos.y, y2)) return { type: 'resize-br' };
        if (pos.x > x1 && pos.x < x2 && pos.y > y1 && pos.y < y2) return { type: 'move' };
    }
    // YOLO 감지박스 클릭 → 선택
    for (let i = 0; i < bboxDraw.yoloDetections.length; i++) {
        const d = bboxDraw.yoloDetections[i];
        const yb = Array.isArray(d.bbox) ? d.bbox : (Array.isArray(d) ? d : null);
        if (!yb) continue;
        if (pos.x > yb[0] && pos.x < yb[2] && pos.y > yb[1] && pos.y < yb[3])
            return { type: 'select-yolo', bbox: [...yb] };
    }
    return { type: 'draw' };
}

function bboxCursorForType(type) {
    if (type === 'resize-tl' || type === 'resize-br') return 'nwse-resize';
    if (type === 'resize-tr' || type === 'resize-bl') return 'nesw-resize';
    if (type === 'move' || type === 'select-yolo') return 'move';
    return 'crosshair';
}

function bboxMouseDown(e) {
    const pos = getCanvasPos(e);
    const hit = getBboxHitTarget(pos);
    if (hit.type === 'select-yolo') {
        // YOLO 박스를 클릭하면 즉시 선택
        bboxDraw.currentBbox = hit.bbox;
        bboxDraw.dragMode = 'move';
        bboxDraw.startPos = pos;
        bboxDraw.startBbox = [...hit.bbox];
        drawVehicleCanvas();
        updateVehicleBboxInfo();
    } else {
        bboxDraw.dragMode = hit.type;
        bboxDraw.startPos = pos;
        bboxDraw.startBbox = bboxDraw.currentBbox ? [...bboxDraw.currentBbox] : null;
    }
}

function bboxMouseMove(e) {
    const pos = getCanvasPos(e);
    if (!bboxDraw.dragMode) {
        bboxDraw.canvas.style.cursor = bboxCursorForType(getBboxHitTarget(pos).type);
        return;
    }
    const { dragMode, startPos, startBbox } = bboxDraw;
    const dx = pos.x - startPos.x, dy = pos.y - startPos.y;
    const img = bboxDraw.img;
    const cx = v => Math.round(Math.max(0, Math.min(v, img.naturalWidth)));
    const cy = v => Math.round(Math.max(0, Math.min(v, img.naturalHeight)));

    if (dragMode === 'draw') {
        bboxDraw.currentBbox = [
            cx(Math.min(startPos.x, pos.x)), cy(Math.min(startPos.y, pos.y)),
            cx(Math.max(startPos.x, pos.x)), cy(Math.max(startPos.y, pos.y))
        ];
    } else if (dragMode === 'move' && startBbox) {
        const [x1, y1, x2, y2] = startBbox, bw = x2-x1, bh = y2-y1;
        const nx1 = cx(x1+dx), ny1 = cy(y1+dy);
        bboxDraw.currentBbox = [nx1, ny1, cx(nx1+bw), cy(ny1+bh)];
    } else if (startBbox) {
        let [x1, y1, x2, y2] = [...startBbox];
        if      (dragMode === 'resize-tl') { x1 = cx(x1+dx); y1 = cy(y1+dy); }
        else if (dragMode === 'resize-tr') { x2 = cx(x2+dx); y1 = cy(y1+dy); }
        else if (dragMode === 'resize-bl') { x1 = cx(x1+dx); y2 = cy(y2+dy); }
        else if (dragMode === 'resize-br') { x2 = cx(x2+dx); y2 = cy(y2+dy); }
        bboxDraw.currentBbox = [Math.min(x1,x2), Math.min(y1,y2), Math.max(x1,x2), Math.max(y1,y2)];
    }
    drawVehicleCanvas();
}

function bboxMouseUp() {
    if (bboxDraw.dragMode) {
        // 드로우 모드에서 너무 작은 박스는 취소
        if (bboxDraw.dragMode === 'draw' && bboxDraw.currentBbox) {
            const [x1,y1,x2,y2] = bboxDraw.currentBbox;
            if ((x2-x1) < 5 || (y2-y1) < 5) bboxDraw.currentBbox = bboxDraw.startBbox;
        }
        bboxDraw.dragMode = null;
        updateVehicleBboxInfo();
    }
}

function drawVehicleCanvas() {
    const { ctx, img, canvas, currentBbox, yoloDetections } = bboxDraw;
    if (!ctx || !img) return;
    const lw = Math.max(2, canvas.width / 400);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);

    // YOLO 감지 박스 — 선택된 것과 다른 경우만 점선으로
    yoloDetections.forEach(det => {
        const b = Array.isArray(det.bbox) ? det.bbox : (Array.isArray(det) ? det : null);
        if (!b || b.length < 4) return;
        // 현재 선택된 박스와 동일하면 스킵 (중복 렌더링 방지)
        if (currentBbox && b[0]===currentBbox[0] && b[1]===currentBbox[1] &&
            b[2]===currentBbox[2] && b[3]===currentBbox[3]) return;
        ctx.save();
        ctx.strokeStyle = 'rgba(34,197,94,0.5)';
        ctx.lineWidth = lw;
        ctx.setLineDash([6, 3]);
        ctx.strokeRect(b[0], b[1], b[2]-b[0], b[3]-b[1]);
        ctx.fillStyle = 'rgba(34,197,94,0.04)';
        ctx.fillRect(b[0], b[1], b[2]-b[0], b[3]-b[1]);
        ctx.restore();
    });

    // 선택/편집 중인 bbox — 진한 초록 + 코너 핸들
    if (currentBbox) {
        const [x1, y1, x2, y2] = currentBbox;
        const hs = getHandleSize();
        ctx.save();
        ctx.fillStyle = 'rgba(34,197,94,0.15)';
        ctx.fillRect(x1, y1, x2-x1, y2-y1);
        ctx.strokeStyle = '#22c55e';
        ctx.lineWidth = lw + 1;
        ctx.setLineDash([]);
        ctx.strokeRect(x1, y1, x2-x1, y2-y1);
        [[x1,y1],[x2,y1],[x1,y2],[x2,y2]].forEach(([hx,hy]) => {
            ctx.fillStyle = '#22c55e';
            ctx.fillRect(hx-hs/2, hy-hs/2, hs, hs);
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = lw;
            ctx.strokeRect(hx-hs/2, hy-hs/2, hs, hs);
        });
        ctx.restore();
    }
}

function updateVehicleBboxInfo() {
    const el = document.getElementById('vehicleBboxInfo');
    if (!el) return;
    const b = bboxDraw.currentBbox;
    el.textContent = b
        ? `선택영역: [${b[0]}, ${b[1]}, ${b[2]}, ${b[3]}]  (${b[2]-b[0]}×${b[3]-b[1]}px)`
        : 'YOLO 감지박스 클릭 또는 직접 드래그하여 영역 선택';
}

function resetVehicleBbox() {
    bboxDraw.currentBbox = bboxDraw.origBbox ? [...bboxDraw.origBbox] : null;
    drawVehicleCanvas();
    updateVehicleBboxInfo();
}

// ── 빠른 재분석 (기존 crop 이미지 그대로) ────────────────────

async function quickReanalyzeVehicle() {
    const id = document.getElementById('vehicleEditId').value;
    if (!id) return;
    if (!confirm('기존 이미지로 재분석하시겠습니까? (제조사/모델 분석 결과가 갱신됩니다)')) return;

    const btn = document.getElementById('vehicleQuickReanalyzeBtn');
    const statusEl = document.getElementById('vehicleReanalyzeStatus');
    const origHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat"></i> 분석 중...';
    statusEl.style.display = 'block';
    statusEl.className = 'mt-2 p-2 rounded small bg-info-subtle';
    statusEl.textContent = '재분석 중...';

    try {
        const resp = await fetch(`${API_BASE}/admin/analyze/${id}`, { method: 'POST' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        const data = await resp.json();
        const result = data.data || {};

        statusEl.className = 'mt-2 p-2 rounded small bg-success-subtle';
        statusEl.textContent = `완료: ${result.manufacturer || '-'} / ${result.model || '-'}`;
        document.getElementById('vehicleEditCurrentAnalysis').textContent =
            `현재: ${result.manufacturer || 'N/A'} / ${result.model || 'N/A'}`;

        if (result.matched_manufacturer_id) {
            const mfSelect = document.getElementById('vehicleEditManufacturer');
            mfSelect.value = result.matched_manufacturer_id;
            await loadVehicleEditModels(result.matched_manufacturer_id, result.matched_model_id);
        }
        loadVehicleData();
    } catch (e) {
        statusEl.className = 'mt-2 p-2 rounded small bg-danger-subtle';
        statusEl.textContent = `오류: ${e.message}`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = origHTML;
    }
}

// ── 재분석 (SSE 스트림) ───────────────────────────────────────

async function reanalyzeVehicleFromModal() {
    const id = document.getElementById('vehicleEditId').value;
    if (!id) return;

    let bbox = bboxDraw.currentBbox;
    // bbox 없으면 전체 이미지를 영역으로 사용
    if (!bbox && bboxDraw.img) {
        bbox = [0, 0, bboxDraw.img.naturalWidth, bboxDraw.img.naturalHeight];
    }
    if (!bbox) {
        showAdminToast('이미지를 불러오는 중입니다. 잠시 후 다시 시도해주세요.', 'error');
        return;
    }

    const btn = document.getElementById('vehicleReanalyzeBtn');
    const statusEl = document.getElementById('vehicleReanalyzeStatus');
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-repeat"></i> 분석 중...';
    statusEl.style.display = 'block';
    statusEl.className = 'mt-2 p-2 rounded small bg-info-subtle';
    statusEl.textContent = '분석 시작 중...';

    const formData = new FormData();
    formData.append('analyzed_id', id);
    formData.append('bbox', JSON.stringify(bbox));

    try {
        const resp = await fetch('/api/analyze-vehicle-stream', { method: 'POST', body: formData });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const lines = buf.split('\n');
            buf = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data:')) continue;
                let data;
                try { data = JSON.parse(line.slice(5).trim()); } catch { continue; }

                if (data.event === 'completed' && data.result) {
                    statusEl.className = 'mt-2 p-2 rounded small bg-success-subtle';
                    statusEl.textContent = `완료: ${data.result.manufacturer || '-'} / ${data.result.model || '-'}`;
                    document.getElementById('vehicleEditCurrentAnalysis').textContent =
                        `현재: ${data.result.manufacturer || 'N/A'} / ${data.result.model || 'N/A'}`;

                    if (data.result.matched_manufacturer_id) {
                        const mfSelect = document.getElementById('vehicleEditManufacturer');
                        mfSelect.value = data.result.matched_manufacturer_id;
                        await loadVehicleEditModels(data.result.matched_manufacturer_id, data.result.matched_model_id);
                    }
                    btn.disabled = false;
                    btn.innerHTML = '<i class="bi bi-arrow-repeat"></i> 재분석 (선택 영역 기준)';
                    loadVehicleData();
                } else if (data.event === 'error') {
                    throw new Error(data.message || '분석 오류');
                } else if (data.message) {
                    statusEl.textContent = data.message;
                }
            }
        }
    } catch (e) {
        statusEl.className = 'mt-2 p-2 rounded small bg-danger-subtle';
        statusEl.textContent = `오류: ${e.message}`;
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-arrow-repeat"></i> 재분석 (선택 영역 기준)';
    }
}

// ── 모달에서 벡터DB 저장 ──────────────────────────────────────

async function saveVehicleFromModal() {
    const id = document.getElementById('vehicleEditId').value;
    if (!id) return;

    const mfSelect = document.getElementById('vehicleEditManufacturer');
    const modelSelect = document.getElementById('vehicleEditModel');

    if (!mfSelect.value || !modelSelect.value) {
        alert('제조사와 모델을 모두 선택해주세요.');
        return;
    }

    if (!confirm('이 데이터를 벡터DB에 저장하시겠습니까?')) return;

    const btn = document.getElementById('vehicleSaveVectorBtn');
    const origHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-hourglass-split"></i> 저장 중...';

    try {
        // 1단계: 제조사/모델 저장
        const newMf = mfSelect.options[mfSelect.selectedIndex].textContent.split(' (')[0];
        const newModel = modelSelect.options[modelSelect.selectedIndex].textContent.split(' (')[0];
        const patchResp = await fetch(`${API_BASE}/admin/review/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                matched_manufacturer_id: parseInt(mfSelect.value),
                matched_model_id: parseInt(modelSelect.value),
                manufacturer: newMf,
                model: newModel
            })
        });
        if (!patchResp.ok) {
            const err = await patchResp.json();
            throw new Error(err.detail || '제조사/모델 저장 실패');
        }

        // 2단계: 벡터DB 등록
        const resp = await fetch(`${API_BASE}/admin/review/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ approved: true })
        });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || '저장 실패');
        }
        showAdminToast('벡터DB에 저장되었습니다', 'success');
        bootstrap.Modal.getInstance(document.getElementById('vehicleEditModal'))?.hide();
        loadVehicleData();
    } catch (e) {
        showAdminToast('저장 실패: ' + e.message, 'error');
        btn.disabled = false;
        btn.innerHTML = origHTML;
    }
}

async function loadVehicleEditModels(manufacturerId, selectedModelId) {
    const modelSelect = document.getElementById('vehicleEditModel');
    if (!manufacturerId) {
        modelSelect.innerHTML = '<option value="">제조사를 먼저 선택하세요</option>';
        return;
    }
    try {
        const resp = await fetch(`${API_BASE}/admin/vehicle-models?manufacturer_id=${manufacturerId}&limit=1000`);
        if (!resp.ok) throw new Error('모델 로드 실패');
        const models = await resp.json();
        modelSelect.innerHTML = '<option value="">모델 선택</option>' +
            models.map(m => `<option value="${m.id}">${m.korean_name} (${m.code})</option>`).join('');
        if (selectedModelId) modelSelect.value = selectedModelId;
    } catch (e) {
        modelSelect.innerHTML = '<option value="">모델 로드 실패</option>';
    }
}

async function saveVehicleEdit() {
    const id = document.getElementById('vehicleEditId').value;
    const mfSelect = document.getElementById('vehicleEditManufacturer');
    const modelSelect = document.getElementById('vehicleEditModel');

    if (!mfSelect.value || !modelSelect.value) {
        alert('제조사와 모델을 모두 선택해주세요.');
        return;
    }

    const newMf = mfSelect.options[mfSelect.selectedIndex].textContent.split(' (')[0];
    const newModel = modelSelect.options[modelSelect.selectedIndex].textContent.split(' (')[0];
    const newMfId = parseInt(mfSelect.value);
    const newModelId = parseInt(modelSelect.value);

    try {
        const resp = await fetch(`${API_BASE}/admin/review/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ matched_manufacturer_id: newMfId, matched_model_id: newModelId, manufacturer: newMf, model: newModel })
        });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || '수정 실패');
        }
        bootstrap.Modal.getInstance(document.getElementById('vehicleEditModal'))?.hide();
        showAdminToast(`수정 완료: ${newMf} ${newModel}`, 'success');
        loadVehicleData();
    } catch (e) {
        alert('오류: ' + e.message);
    }
}


async function deleteVehicle(id) {
    if (!confirm('이 데이터를 삭제하시겠습니까?\n검증 완료 데이터는 벡터DB 레코드도 함께 삭제됩니다.\n삭제된 데이터는 복구할 수 없습니다.')) return;

    try {
        const resp = await fetch(`${API_BASE}/admin/review/${id}`, { method: 'DELETE' });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || '삭제 실패');
        }
        showAdminToast('삭제되었습니다', 'success');
        loadVehicleData();
    } catch (e) {
        showAdminToast('삭제 실패: ' + e.message, 'error');
    }
}

async function deleteSelectedVehicles() {
    if (vehicleState.selectedIds.size === 0) {
        showAdminToast('선택된 항목이 없습니다', 'error');
        return;
    }
    if (!confirm(`선택한 ${vehicleState.selectedIds.size}개 레코드를 삭제하시겠습니까?\n삭제된 데이터는 복구할 수 없습니다.`)) return;

    let deleted = 0, failed = 0;
    for (const id of vehicleState.selectedIds) {
        try {
            const resp = await fetch(`${API_BASE}/admin/review/${id}`, { method: 'DELETE' });
            if (resp.ok) deleted++; else failed++;
        } catch (e) { failed++; }
    }
    showAdminToast(`삭제 완료: ${deleted}개${failed ? ` (실패: ${failed}개)` : ''}`, deleted > 0 ? 'success' : 'error');
    loadVehicleData();
}

async function saveSelectedToVectorDB() {
    if (vehicleState.selectedIds.size === 0) {
        showAdminToast('선택된 항목이 없습니다', 'error');
        return;
    }
    if (!confirm(`선택한 ${vehicleState.selectedIds.size}개 레코드를 벡터DB에 저장하시겠습니까?`)) return;

    let saved = 0, failed = 0;
    for (const id of vehicleState.selectedIds) {
        try {
            const resp = await fetch(`${API_BASE}/admin/review/${id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ approved: true })
            });
            if (resp.ok) saved++; else failed++;
        } catch (e) { failed++; }
    }
    showAdminToast(`저장 완료: ${saved}개${failed ? ` (실패: ${failed}개)` : ''}`, saved > 0 ? 'success' : 'error');
    loadVehicleData();
}

// 인라인 제조사 추가 (vehicleEditModal용)
function openVehicleInlineAddManufacturer() {
    document.getElementById('vehicleInlineAddManufacturer').style.display = 'block';
}
function closeVehicleInlineAddManufacturer() {
    const el = document.getElementById('vehicleInlineAddManufacturer');
    if (el) el.style.display = 'none';
    ['vehicleInlineMfCode', 'vehicleInlineMfKorean', 'vehicleInlineMfEnglish'].forEach(id => {
        const e2 = document.getElementById(id); if (e2) e2.value = '';
    });
    const dom = document.getElementById('vehicleInlineMfDomestic');
    if (dom) dom.checked = false;
}
async function saveVehicleInlineManufacturer() {
    const code = document.getElementById('vehicleInlineMfCode').value.trim();
    const korean = document.getElementById('vehicleInlineMfKorean').value.trim();
    const english = document.getElementById('vehicleInlineMfEnglish').value.trim();
    const isDomestic = document.getElementById('vehicleInlineMfDomestic').checked;
    if (!code || !korean || !english) { alert('코드, 한글명, 영문명을 모두 입력해주세요.'); return; }
    try {
        const resp = await fetch(`${API_BASE}/admin/manufacturers`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, english_name: english, korean_name: korean, is_domestic: isDomestic })
        });
        if (!resp.ok) { const e = await resp.json(); throw new Error(e.detail || '추가 실패'); }
        const newMf = await resp.json();
        vehicleState.editManufacturers.push(newMf);
        const mfSelect = document.getElementById('vehicleEditManufacturer');
        mfSelect.innerHTML = '<option value="">제조사 선택</option>' +
            vehicleState.editManufacturers.map(mf =>
                `<option value="${mf.id}" data-code="${mf.code}">${mf.korean_name} (${mf.code})</option>`).join('');
        mfSelect.value = newMf.id;
        await loadVehicleEditModels(newMf.id, null);
        closeVehicleInlineAddManufacturer();
        showAdminToast(`제조사 "${korean}" 추가됨`, 'success');
    } catch (e) { alert('오류: ' + e.message); }
}

// 인라인 모델 추가 (vehicleEditModal용)
function openVehicleInlineAddModel() {
    if (!document.getElementById('vehicleEditManufacturer').value) {
        alert('제조사를 먼저 선택해주세요.'); return;
    }
    document.getElementById('vehicleInlineAddModel').style.display = 'block';
}
function closeVehicleInlineAddModel() {
    const el = document.getElementById('vehicleInlineAddModel');
    if (el) el.style.display = 'none';
    ['vehicleInlineModelCode', 'vehicleInlineModelKorean', 'vehicleInlineModelEnglish'].forEach(id => {
        const e2 = document.getElementById(id); if (e2) e2.value = '';
    });
}
async function saveVehicleInlineModel() {
    const mfSelect = document.getElementById('vehicleEditManufacturer');
    const mfId = parseInt(mfSelect.value);
    const mfCode = mfSelect.options[mfSelect.selectedIndex]?.dataset?.code || '';
    const code = document.getElementById('vehicleInlineModelCode').value.trim();
    const korean = document.getElementById('vehicleInlineModelKorean').value.trim();
    const english = document.getElementById('vehicleInlineModelEnglish').value.trim();
    if (!code || !korean || !english) { alert('코드, 한글명, 영문명을 모두 입력해주세요.'); return; }
    try {
        const resp = await fetch(`${API_BASE}/admin/vehicle-models`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, manufacturer_id: mfId, manufacturer_code: mfCode, english_name: english, korean_name: korean })
        });
        if (!resp.ok) { const e = await resp.json(); throw new Error(e.detail || '추가 실패'); }
        const newModel = await resp.json();
        await loadVehicleEditModels(mfId, newModel.id);
        closeVehicleInlineAddModel();
        showAdminToast(`모델 "${korean}" 추가됨`, 'success');
    } catch (e) { alert('오류: ' + e.message); }
}
