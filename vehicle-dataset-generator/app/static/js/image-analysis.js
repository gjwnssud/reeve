/**
 * 이미지 분석 기능
 * 단일/다중 이미지 처리, 차량 감지, 바운딩 박스 관리
 */

window.ImageAnalysis = {
    /**
     * 단일 이미지 인터페이스 표시
     */
    showSingleImageInterface(file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const image = new Image();
            image.onload = function() {
                window.AppState.currentImage = image;
                if (window.BoundingBox && window.BoundingBox.setupCanvas) {
                    window.BoundingBox.setupCanvas();
                    window.BoundingBox.drawImageAndDetectVehicles(e.target.result);
                }
            };
            image.src = e.target.result;
        };
        reader.readAsDataURL(file);
    },

    /**
     * 다중 이미지 인터페이스 표시
     */
    showMultiImageInterface(files) {
        if (window.MultiImage && window.MultiImage.startDetection) {
            window.MultiImage.startDetection(files);
        }
    }
};

/**
 * 단일 이미지 분석 함수들
 */
async function analyzeSelectedRegion() {
    if (!window.AppState.boundingBox || !window.AppState.currentImage) {
        alert('먼저 이미지를 선택하고 분석할 영역을 설정해주세요.');
        return;
    }
    
    const canvas = window.AppState.canvas;
    const image = window.AppState.currentImage;
    const bbox = window.AppState.boundingBox;
    
    // 캔버스 좌표를 원본 이미지 좌표로 변환
    const scaleX = image.width / canvas.width;
    const scaleY = image.height / canvas.height;
    
    const originalBbox = [
        Math.round(bbox.x * scaleX),
        Math.round(bbox.y * scaleY),
        Math.round((bbox.x + bbox.width) * scaleX),
        Math.round((bbox.y + bbox.height) * scaleY)
    ];
    
    window.Utils.showLoading('image');
    window.Utils.hideResult('image');
    
    try {
        // 원본 이미지를 base64로 변환
        const canvas2 = document.createElement('canvas');
        const ctx2 = canvas2.getContext('2d');
        canvas2.width = image.width;
        canvas2.height = image.height;
        ctx2.drawImage(image, 0, 0);
        const imageDataURL = canvas2.toDataURL('image/jpeg');
        
        const response = await window.Utils.apiRequest(window.API.ENDPOINTS.ANALYZE_REGION, {
            method: 'POST',
            body: JSON.stringify({
                image_data: imageDataURL,
                bbox: originalBbox
            })
        });
        
        window.Utils.hideLoading('image');
        
        if (response.success) {
            window.displaySingleResult('image', response.result);
        } else {
            window.Utils.displayError('image', response.error || '분석 중 오류가 발생했습니다.');
        }
        
    } catch (error) {
        window.Utils.hideLoading('image');
        window.Utils.displayError('image', '분석 중 오류가 발생했습니다: ' + error.message);
    }
}

async function analyzeFullImage() {
    if (!window.AppState.currentImage) {
        alert('먼저 이미지를 선택해주세요.');
        return;
    }
    
    window.Utils.showLoading('image');
    window.Utils.hideResult('image');
    
    try {
        const image = window.AppState.currentImage;
        
        // 원본 이미지를 base64로 변환
        const canvas2 = document.createElement('canvas');
        const ctx2 = canvas2.getContext('2d');
        canvas2.width = image.width;
        canvas2.height = image.height;
        ctx2.drawImage(image, 0, 0);
        const imageDataURL = canvas2.toDataURL('image/jpeg');
        
        const response = await window.Utils.apiRequest(window.API.ENDPOINTS.ANALYZE_REGION, {
            method: 'POST',
            body: JSON.stringify({
                image_data: imageDataURL,
                bbox: null  // 전체 이미지 분석
            })
        });
        
        window.Utils.hideLoading('image');
        
        if (response.success) {
            window.displaySingleResult('image', response.result);
        } else {
            window.Utils.displayError('image', response.error || '분석 중 오류가 발생했습니다.');
        }
        
    } catch (error) {
        window.Utils.hideLoading('image');
        window.Utils.displayError('image', '분석 중 오류가 발생했습니다: ' + error.message);
    }
}

// 전역 함수 등록
window.analyzeSelectedRegion = analyzeSelectedRegion;
window.analyzeFullImage = analyzeFullImage;
