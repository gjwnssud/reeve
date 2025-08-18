// Canvas 기반 바운딩 박스 처리 클래스
class BoundingBoxHandler {
    constructor(imageElement, vehicles, onBboxChange) {
        this.imageElement = imageElement;
        this.vehicles = vehicles;
        this.onBboxChange = onBboxChange;
        this.canvas = null;
        this.ctx = null;
        this.originalBoxes = []; // 원본 박스 저장
        this.selectedBoxIndex = -1;
        this.isDragging = false;
        this.isResizing = false;
        this.dragStart = { x: 0, y: 0 };
        this.dragOffset = { x: 0, y: 0 };
        
        this.init();
    }
    
    init() {
        // 이미지 컨테이너 생성
        this.createImageContainer();
        
        // 원본 바운딩 박스 저장
        this.originalBoxes = this.vehicles.map(vehicle => [...vehicle.bbox]);
        
        // Canvas 생성
        this.createCanvas();
        
        // 이벤트 리스너 추가
        this.addEventListeners();
        
        // 초기 렌더링
        this.render();
    }
    
    createImageContainer() {
        // 이미지가 이미 컨테이너에 있는지 확인
        if (this.imageElement.parentNode && this.imageElement.parentNode.classList.contains('image-container')) {
            this.container = this.imageElement.parentNode;
        } else {
            // 기존 이미지를 컨테이너로 감싸기
            const container = document.createElement('div');
            container.className = 'image-container';
            container.style.position = 'relative';
            container.style.display = 'inline-block';
            
            const parent = this.imageElement.parentNode;
            parent.insertBefore(container, this.imageElement);
            container.appendChild(this.imageElement);
            
            this.container = container;
        }
        
        // 이미지에 클래스 추가
        if (!this.imageElement.classList.contains('image-with-bbox')) {
            this.imageElement.classList.add('image-with-bbox');
        }
    }
    
    createCanvas() {
        // 기존 캔버스 제거
        const existingCanvas = this.container.querySelector('.bbox-canvas');
        if (existingCanvas) {
            existingCanvas.remove();
        }
        
        // 새 캔버스 생성
        this.canvas = document.createElement('canvas');
        this.canvas.className = 'bbox-canvas';
        this.canvas.style.position = 'absolute';
        this.canvas.style.top = '0';
        this.canvas.style.left = '0';
        this.canvas.style.pointerEvents = 'auto';
        this.canvas.style.cursor = 'default';
        this.canvas.style.zIndex = '10';
        
        // 캔버스 크기 설정
        this.updateCanvasSize();
        
        // 컨텍스트 가져오기
        this.ctx = this.canvas.getContext('2d');
        
        // 컨테이너에 추가
        this.container.appendChild(this.canvas);
        
        console.log('Canvas 생성 완료:', this.canvas);
    }
    
    updateCanvasSize() {
        if (!this.canvas || !this.imageElement) return;
        
        this.canvas.width = this.imageElement.offsetWidth;
        this.canvas.height = this.imageElement.offsetHeight;
        this.canvas.style.width = this.imageElement.offsetWidth + 'px';
        this.canvas.style.height = this.imageElement.offsetHeight + 'px';
        
        console.log('Canvas 크기 업데이트:', {
            width: this.canvas.width,
            height: this.canvas.height,
            imageWidth: this.imageElement.offsetWidth,
            imageHeight: this.imageElement.offsetHeight
        });
    }
    
    addEventListeners() {
        console.log('Canvas 이벤트 리스너 추가');
        
        // 마우스 이벤트
        this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
        this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
        this.canvas.addEventListener('mouseup', (e) => this.onMouseUp(e));
        this.canvas.addEventListener('mouseleave', (e) => this.onMouseUp(e));
        
        // 더블클릭으로 리셋
        this.canvas.addEventListener('dblclick', (e) => this.onDoubleClick(e));
        
        // 윈도우 리사이즈
        window.addEventListener('resize', () => this.onWindowResize());
        
        // 이미지 로드 완료 후 캔버스 크기 재조정
        if (this.imageElement.complete) {
            this.updateCanvasSize();
            this.render();
        } else {
            this.imageElement.onload = () => {
                this.updateCanvasSize();
                this.render();
            };
        }
    }
    
    onMouseDown(e) {
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        console.log('Canvas 마우스 다운:', x, y);
        
        // 클릭된 바운딩 박스 찾기
        const clickedBox = this.findBoxAtPoint(x, y);
        
        if (clickedBox !== -1) {
            this.selectedBoxIndex = clickedBox;
            
            // 리사이즈 핸들 클릭 확인
            if (this.isResizeHandle(x, y, clickedBox)) {
                this.isResizing = true;
                this.canvas.style.cursor = 'se-resize';
                console.log('리사이즈 시작');
            } else {
                this.isDragging = true;
                this.canvas.style.cursor = 'grabbing';
                
                // 드래그 시작점과 박스와의 오프셋 계산
                const box = this.getScreenBox(clickedBox);
                this.dragOffset = {
                    x: x - box.x,
                    y: y - box.y
                };
                console.log('드래그 시작, 오프셋:', this.dragOffset);
            }
            
            this.dragStart = { x, y };
            this.render();
        } else {
            this.selectedBoxIndex = -1;
            this.render();
        }
    }
    
    onMouseMove(e) {
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        if (this.isDragging && this.selectedBoxIndex >= 0) {
            this.dragBox(x, y);
        } else if (this.isResizing && this.selectedBoxIndex >= 0) {
            this.resizeBox(x, y);
        } else {
            // 커서 변경
            const hoveredBox = this.findBoxAtPoint(x, y);
            if (hoveredBox >= 0) {
                if (this.isResizeHandle(x, y, hoveredBox)) {
                    this.canvas.style.cursor = 'se-resize';
                } else {
                    this.canvas.style.cursor = 'move';
                }
            } else {
                this.canvas.style.cursor = 'default';
            }
        }
    }
    
    onMouseUp(e) {
        if (this.isDragging || this.isResizing) {
            console.log('드래그/리사이즈 완료');
            
            this.isDragging = false;
            this.isResizing = false;
            this.canvas.style.cursor = 'default';
            
            // 변경 콜백 호출
            if (this.onBboxChange) {
                this.onBboxChange(this.vehicles);
            }
        }
    }
    
    onDoubleClick(e) {
        const rect = this.canvas.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        const clickedBox = this.findBoxAtPoint(x, y);
        if (clickedBox >= 0) {
            this.resetBox(clickedBox);
        }
    }
    
    onWindowResize() {
        setTimeout(() => {
            this.updateCanvasSize();
            this.render();
        }, 100);
    }
    
    findBoxAtPoint(x, y) {
        for (let i = this.vehicles.length - 1; i >= 0; i--) {
            const box = this.getScreenBox(i);
            if (x >= box.x && x <= box.x + box.width &&
                y >= box.y && y <= box.y + box.height) {
                return i;
            }
        }
        return -1;
    }
    
    isResizeHandle(x, y, boxIndex) {
        const box = this.getScreenBox(boxIndex);
        const handleSize = 8;
        const handleX = box.x + box.width - handleSize/2;
        const handleY = box.y + box.height - handleSize/2;
        
        return x >= handleX && x <= handleX + handleSize &&
               y >= handleY && y <= handleY + handleSize;
    }
    
    getScreenBox(index) {
        const vehicle = this.vehicles[index];
        const bbox = vehicle.bbox;
        
        const scaleX = this.canvas.width / this.imageElement.naturalWidth;
        const scaleY = this.canvas.height / this.imageElement.naturalHeight;
        
        return {
            x: bbox[0] * scaleX,
            y: bbox[1] * scaleY,
            width: (bbox[2] - bbox[0]) * scaleX,
            height: (bbox[3] - bbox[1]) * scaleY
        };
    }
    
    dragBox(mouseX, mouseY) {
        const vehicle = this.vehicles[this.selectedBoxIndex];
        const scaleX = this.imageElement.naturalWidth / this.canvas.width;
        const scaleY = this.imageElement.naturalHeight / this.canvas.height;
        
        // 새 위치 계산 (드래그 오프셋 고려)
        const newX = (mouseX - this.dragOffset.x) * scaleX;
        const newY = (mouseY - this.dragOffset.y) * scaleY;
        
        // 바운딩 박스 크기
        const width = vehicle.bbox[2] - vehicle.bbox[0];
        const height = vehicle.bbox[3] - vehicle.bbox[1];
        
        // 이미지 경계 내에서만 이동
        const clampedX = Math.max(0, Math.min(newX, this.imageElement.naturalWidth - width));
        const clampedY = Math.max(0, Math.min(newY, this.imageElement.naturalHeight - height));
        
        // 바운딩 박스 업데이트
        vehicle.bbox = [
            clampedX,
            clampedY,
            clampedX + width,
            clampedY + height
        ];
        
        this.render();
    }
    
    resizeBox(mouseX, mouseY) {
        const vehicle = this.vehicles[this.selectedBoxIndex];
        const scaleX = this.imageElement.naturalWidth / this.canvas.width;
        const scaleY = this.imageElement.naturalHeight / this.canvas.height;
        
        // 새 크기 계산
        let newX2 = mouseX * scaleX;
        let newY2 = mouseY * scaleY;
        
        // 최소 크기 및 이미지 경계 제한
        newX2 = Math.max(vehicle.bbox[0] + 20, Math.min(newX2, this.imageElement.naturalWidth));
        newY2 = Math.max(vehicle.bbox[1] + 20, Math.min(newY2, this.imageElement.naturalHeight));
        
        // 바운딩 박스 업데이트
        vehicle.bbox[2] = newX2;
        vehicle.bbox[3] = newY2;
        
        this.render();
    }
    
    resetBox(index) {
        if (index >= 0 && index < this.vehicles.length && index < this.originalBoxes.length) {
            this.vehicles[index].bbox = [...this.originalBoxes[index]];
            this.render();
            
            if (this.onBboxChange) {
                this.onBboxChange(this.vehicles);
            }
            
            console.log(`박스 ${index} 리셋 완료`);
        }
    }
    
    render() {
        if (!this.ctx) return;
        
        // 캔버스 지우기
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // 모든 바운딩 박스 그리기
        this.vehicles.forEach((vehicle, index) => {
            this.drawBoundingBox(vehicle, index);
        });
    }
    
    drawBoundingBox(vehicle, index) {
        const box = this.getScreenBox(index);
        const isSelected = index === this.selectedBoxIndex;
        
        // 박스 그리기
        this.ctx.strokeStyle = isSelected ? '#00ff00' : '#ff4444';
        this.ctx.lineWidth = 2;
        this.ctx.fillStyle = isSelected ? 'rgba(0, 255, 0, 0.1)' : 'rgba(255, 68, 68, 0.1)';
        
        this.ctx.fillRect(box.x, box.y, box.width, box.height);
        this.ctx.strokeRect(box.x, box.y, box.width, box.height);
        
        // 리사이즈 핸들 그리기
        if (isSelected) {
            const handleSize = 8;
            const handleX = box.x + box.width - handleSize/2;
            const handleY = box.y + box.height - handleSize/2;
            
            this.ctx.fillStyle = '#ff4444';
            this.ctx.fillRect(handleX, handleY, handleSize, handleSize);
            this.ctx.strokeStyle = '#ffffff';
            this.ctx.lineWidth = 1;
            this.ctx.strokeRect(handleX, handleY, handleSize, handleSize);
        }
        
        // 라벨 그리기
        const label = `${vehicle.class_name} ${(vehicle.confidence * 100).toFixed(1)}%`;
        const labelWidth = this.ctx.measureText(label).width + 10;
        const labelHeight = 20;

        // 라벨 위치 계산 (캔버스 경계 내에 유지)
        let labelX = box.x;
        let labelY = box.y - 25;

        // 좌측 경계 체크
        if (labelX < 0) labelX = 0;
        // 우측 경계 체크
        if (labelX + labelWidth > this.canvas.width) {
            labelX = this.canvas.width - labelWidth;
        }
        // 상단 경계 체크 (라벨이 위로 나가면 박스 아래로 이동)
        if (labelY < 0) {
            labelY = box.y + box.height + 5;
        }
        // 하단 경계 체크
        if (labelY + labelHeight > this.canvas.height) {
            labelY = this.canvas.height - labelHeight;
        }

        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
        this.ctx.fillRect(labelX, labelY, labelWidth, labelHeight);

        this.ctx.fillStyle = '#ffffff';
        this.ctx.font = '12px Arial';
        this.ctx.fillText(label, labelX + 5, labelY + 15);

        // 리셋 버튼 영역 (더블클릭 안내)
        if (isSelected) {
            const resetLabel = '더블클릭: 리셋';
            const resetWidth = this.ctx.measureText(resetLabel).width + 10;

            // 리셋 버튼 위치 계산
            let resetX = box.x + box.width - resetWidth;
            let resetY = box.y - 25;

            // 경계 체크
            if (resetX < 0) resetX = 0;
            if (resetX + resetWidth > this.canvas.width) {
                resetX = this.canvas.width - resetWidth;
            }
            if (resetY < 0) {
                resetY = box.y + box.height + 5;
            }
            if (resetY + labelHeight > this.canvas.height) {
                resetY = this.canvas.height - labelHeight;
            }

            this.ctx.fillStyle = 'rgba(0, 123, 255, 0.8)';
            this.ctx.fillRect(resetX, resetY, resetWidth, labelHeight);

            this.ctx.fillStyle = '#ffffff';
            this.ctx.font = '11px Arial';
            this.ctx.fillText(resetLabel, resetX + 5, resetY + 15);
        }
    }
    
    getBoundingBoxes() {
        return this.vehicles.map(vehicle => vehicle.bbox);
    }
    
    destroy() {
        console.log('BoundingBoxHandler 삭제');
        
        // 이벤트 리스너 제거
        if (this.canvas) {
            this.canvas.remove();
        }
        
        // 윈도우 리사이즈 이벤트 제거 (실제로는 다른 인스턴스와 공유되므로 주의)
        // window.removeEventListener('resize', this.onWindowResize);
        
        this.canvas = null;
        this.ctx = null;
        this.vehicles = null;
        this.selectedBoxIndex = -1;
        this.isDragging = false;
        this.isResizing = false;
    }
}

// 전역에서 접근 가능하도록 설정
window.BoundingBoxHandler = BoundingBoxHandler;
