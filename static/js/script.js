// Các hàm chung có thể sử dụng trên nhiều trang
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('vi-VN');
}

// Hiển thị thông báo
function showAlert(message, type = 'success') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.role = 'alert';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container');
    container.prepend(alertDiv);
    
    setTimeout(() => {
        alertDiv.classList.remove('show');
        setTimeout(() => alertDiv.remove(), 150);
    }, 3000);
}
// Hiển thị danh sách nhạc sĩ mới nhất
function loadLatestNhacSi() {
    fetch('/api/nhacsi/latest')
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('latestNhacSiList');
            container.innerHTML = '';
            
            data.forEach(nhacsi => {
                const item = document.createElement('a');
                item.href = `/nhacsi/${nhacsi.idnhacsi}`;  // Liên kết tới trang chi tiết
                item.className = 'list-group-item list-group-item-action';
                item.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h6 class="mb-1">${nhacsi.tennhacsi}</h6>
                            <small class="text-muted">Ngày sinh: ${nhacsi.ngaysinh || 'Chưa cập nhật'}</small>
                        </div>
                        <span class="badge bg-primary rounded-pill">${nhacsi.ngay_them}</span>
                    </div>
                `;
                container.appendChild(item);
            });
        });
}

// Hiển thị danh sách ca sĩ mới nhất
// Hiển thị danh sách ca sĩ mới nhất
function loadLatestCaSi() {
    fetch('/api/casi/latest')
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('latestCaSiList');
            container.innerHTML = '';
            
            if (data.length === 0) {
                container.innerHTML = '<div class="list-group-item text-center py-3">Chưa có dữ liệu</div>';
                return;
            }
            
            data.forEach(casi => {
                const item = document.createElement('a');
                item.href = `/casi/${casi.idcasi}`;  // Liên kết tới trang chi tiết ca sĩ
                item.className = 'list-group-item list-group-item-action';
                item.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h6 class="mb-1">${casi.tencasi}</h6>
                            <small class="text-muted">Ngày sinh: ${casi.ngaysinh || 'Chưa cập nhật'}</small>
                        </div>
                        <span class="badge bg-success rounded-pill">${casi.ngay_them}</span>
                    </div>
                `;
                container.appendChild(item);
            });
        })
        .catch(error => {
            console.error('Error:', error);
            document.getElementById('latestCaSiList').innerHTML = `
                <div class="list-group-item text-center text-danger py-3">
                    Đã xảy ra lỗi khi tải danh sách ca sĩ
                    <button onclick="loadLatestCaSi()" class="btn btn-sm btn-danger mt-2">
                        <i class="fas fa-sync-alt me-1"></i>Thử lại
                    </button>
                </div>
            `;
        });
}

// Gọi hàm khi trang được tải
document.addEventListener('DOMContentLoaded', function() {
    loadLatestNhacSi();
    loadLatestCaSi();
});

// Hiển thị bản nhạc nổi bật
function loadFeaturedSongs() {
    fetch('/api/bannhac/noibat')
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('featuredSongs');
            container.innerHTML = '';
            
            if (data.length === 0) {
                container.innerHTML = `
                    <div class="col-12 text-center py-3">
                        <p class="text-muted">Chưa có bản nhạc nổi bật</p>
                    </div>
                `;
                return;
            }
            
            data.forEach(song => {
                const col = document.createElement('div');
                col.className = 'col-md-6 col-lg-4 col-xl-3 mb-4';
                col.innerHTML = `
                    <div class="card h-100 song-card">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h5 class="card-title">${song.tenbannhac}</h5>
                                    <p class="card-text text-muted mb-1">
                                        <i class="fas fa-user-edit me-1"></i>${song.tennhacsi}
                                    </p>
                                </div>
                                <span class="badge bg-danger rounded-pill">
                                    ${song.soluong_banthuam} <i class="fas fa-microphone ms-1"></i>
                                </span>
                            </div>
                        </div>
                        <div class="card-footer bg-transparent">
                            <small class="text-muted">
                                <i class="far fa-calendar-alt me-1"></i>${song.ngay_them}
                            </small>
                            <a href="/bannhac/detail/${song.idbannhac}" class="btn btn-sm btn-outline-danger float-end">
                                Chi tiết
                            </a>
                        </div>
                    </div>
                `;
                container.appendChild(col);
            });
        })
        .catch(error => {
            console.error('Error:', error);
            document.getElementById('featuredSongs').innerHTML = `
                <div class="col-12 text-center py-3 text-danger">
                    <p>Đã xảy ra lỗi khi tải danh sách bản nhạc</p>
                    <button class="btn btn-sm btn-danger" onclick="loadFeaturedSongs()">
                        <i class="fas fa-sync-alt me-1"></i>Thử lại
                    </button>
                </div>
            `;
        });
}

// Thêm vào sự kiện DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
    loadFeaturedSongs();
    // ... các hàm load khác
});

// Hiển thị bản nhạc nổi bật
function loadFeaturedSongs() {
    fetch('/api/bannhac/noibat')
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('featuredSongs');
            container.innerHTML = '';
            
            if (data.length === 0) {
                container.innerHTML = `
                    <div class="col-12 text-center py-3">
                        <p class="text-muted">Chưa có bản nhạc nổi bật</p>
                    </div>
                `;
                return;
            }
            
            data.forEach(song => {
                const col = document.createElement('div');
                col.className = 'col-md-6 col-lg-4 col-xl-3 mb-4';
                col.innerHTML = `
                    <div class="card h-100 song-card">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <h5 class="card-title">
                                        <a href="/bannhac/${song.idbannhac}" class="text-decoration-none text-dark">
                                            ${song.tenbannhac}
                                        </a>
                                    </h5>
                                    <p class="card-text text-muted mb-1">
                                        <i class="fas fa-user-edit me-1"></i>
                                        <a href="/nhacsi/${song.idnhacsi}" class="text-decoration-none">
                                            ${song.tennhacsi}
                                        </a>
                                    </p>
                                </div>
                                <span class="badge bg-danger rounded-pill">
                                    ${song.soluong_banthuam} <i class="fas fa-microphone ms-1"></i>
                                </span>
                            </div>
                        </div>
                        <div class="card-footer bg-transparent">
                            <small class="text-muted">
                                <i class="far fa-calendar-alt me-1"></i>${song.ngay_them}
                            </small>
                            <a href="/bannhac/${song.idbannhac}" class="btn btn-sm btn-outline-danger float-end">
                                Chi tiết
                            </a>
                        </div>
                    </div>
                `;
                container.appendChild(col);
            });
        })
        .catch(error => {
            console.error('Error:', error);
            document.getElementById('featuredSongs').innerHTML = `
                <div class="col-12 text-center py-3 text-danger">
                    <p>Đã xảy ra lỗi khi tải danh sách bản nhạc</p>
                    <button class="btn btn-sm btn-danger" onclick="loadFeaturedSongs()">
                        <i class="fas fa-sync-alt me-1"></i>Thử lại
                    </button>
                </div>
            `;
        });
}

// Gọi hàm khi trang được tải
document.addEventListener('DOMContentLoaded', function() {
    loadFeaturedSongs();
});

// Hiển thị bản thu âm nổi bật
function loadFeaturedRecordings() {
    fetch('/api/banthuam/noibat')
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('featuredRecordings');
            container.innerHTML = '';
            
            if (data.length === 0) {
                container.innerHTML = `
                    <div class="col-12 text-center py-3">
                        <p class="text-muted">Chưa có bản thu âm nổi bật</p>
                    </div>
                `;
                return;
            }
            
            data.forEach(recording => {
                const col = document.createElement('div');
                col.className = 'col-md-6 col-lg-4 mb-4';
                col.innerHTML = `
                    <div class="card h-100 recording-card">
                        <div class="card-body">
                            <div class="d-flex align-items-start mb-3">
                                <img src="${recording.anhdaidien || '/static/images/default-avatar.jpg'}" 
                                     class="rounded-circle me-3" 
                                     width="60" 
                                     height="60"
                                     style="object-fit: cover;">
                                <div>
                                    <h5 class="mb-1">
                                        <a href="/banthuam/detail/${recording.idbanthuam}" class="text-decoration-none">
                                            ${recording.tenbannhac}
                                        </a>
                                    </h5>
                                    <p class="mb-0 text-muted">
                                        <a href="/casi/${recording.idcasi}" class="text-decoration-none">
                                            ${recording.tencasi}
                                        </a>
                                    </p>
                                </div>
                            </div>
                            <div class="d-flex justify-content-between align-items-center">
                                <span class="badge bg-warning text-dark">
                                    <i class="fas fa-heart me-1"></i>${recording.luot_thich || 0}
                                </span>
                                <small class="text-muted">
                                    <i class="far fa-calendar-alt me-1"></i>${recording.ngaythuam || recording.ngay_them}
                                </small>
                            </div>
                        </div>
                        <div class="card-footer bg-transparent">
                            <button class="btn btn-sm btn-outline-warning me-2">
                                <i class="fas fa-play me-1"></i>Nghe
                            </button>
                            <a href="/banthuam/detail/${recording.idbanthuam}" class="btn btn-sm btn-outline-dark">
                                Chi tiết
                            </a>
                        </div>
                    </div>
                `;
                container.appendChild(col);
            });
        })
        .catch(error => {
            console.error('Error:', error);
            document.getElementById('featuredRecordings').innerHTML = `
                <div class="col-12 text-center py-3 text-danger">
                    <p>Đã xảy ra lỗi khi tải bản thu âm nổi bật</p>
                    <button class="btn btn-sm btn-warning" onclick="loadFeaturedRecordings()">
                        <i class="fas fa-sync-alt me-1"></i>Thử lại
                    </button>
                </div>
            `;
        });
}

// Gọi hàm khi trang được tải
document.addEventListener('DOMContentLoaded', function() {
    loadFeaturedRecordings();
});
