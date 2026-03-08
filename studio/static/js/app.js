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
    initTabs();
    initModals();
    loadManufacturers();

    // 이벤트 리스너 등록
    document.getElementById('addManufacturerBtn').addEventListener('click', () => openManufacturerModal());
    document.getElementById('addModelBtn').addEventListener('click', () => openModelModal());
    document.getElementById('manufacturerForm').addEventListener('submit', handleManufacturerSubmit);
    document.getElementById('modelForm').addEventListener('submit', handleModelSubmit);
    document.getElementById('refreshReviewBtn').addEventListener('click', loadReviewQueue);
    document.getElementById('analyzeAllBtn').addEventListener('click', startBatchAnalysis);
    document.getElementById('deleteAllBtn').addEventListener('click', startBatchDelete);

    // 필터 이벤트
    document.querySelectorAll('input[name="domesticFilter"]').forEach(radio => {
        radio.addEventListener('change', filterManufacturers);
    });

    document.getElementById('manufacturerFilter').addEventListener('change', filterModels);
});

// 탭 전환
function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.dataset.tab;

            // 모든 탭 비활성화
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));

            // 선택된 탭 활성화
            button.classList.add('active');
            document.getElementById(tabName).classList.add('active');

            // 탭별 데이터 로드
            if (tabName === 'manufacturers') {
                loadManufacturers();
            } else if (tabName === 'models') {
                loadModels();
            } else if (tabName === 'review') {
                loadReviewQueue();
            }
        });
    });
}

// 모달 초기화
function initModals() {
    const modals = document.querySelectorAll('.modal');

    modals.forEach(modal => {
        const closeBtns = modal.querySelectorAll('.btn-close');

        closeBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                modal.style.display = 'none';
            });
        });

        // 모달 바깥 클릭 시 닫기
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        });
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
    ];

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

    modal.querySelector('h3').textContent = manufacturerId ? '제조사 수정' : '제조사 추가';
    modal.style.display = 'block';
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
        document.getElementById('manufacturerModal').style.display = 'none';
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

    modal.querySelector('h3').textContent = modelId ? '모델 수정' : '모델 추가';
    modal.style.display = 'block';
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
        document.getElementById('modelModal').style.display = 'none';
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

    modal.style.display = 'block';
}

// 제조사 변경시 모델 목록 업데이트
document.addEventListener('DOMContentLoaded', () => {
    const mfSelect = document.getElementById('editManufacturer');
    if (mfSelect) {
        mfSelect.addEventListener('change', () => {
            const mfId = mfSelect.value ? parseInt(mfSelect.value) : null;
            loadModelsForManufacturer(mfId, null);
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

        document.getElementById('imageDetailModal').style.display = 'none';

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
