-- --------------------------------------------------------
-- Máy chủ:                      127.0.0.1
-- Server version:               9.1.0 - MySQL Community Server - GPL
-- Server OS:                    Win64
-- HeidiSQL Phiên bản:           12.8.0.6908
-- --------------------------------------------------------

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET NAMES utf8 */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;


-- Dumping database structure for mymusic
DROP DATABASE IF EXISTS `mymusic`;
CREATE DATABASE IF NOT EXISTS `mymusic` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;
USE `mymusic`;

-- Dumping structure for table mymusic.bannhac
CREATE TABLE IF NOT EXISTS `bannhac` (
  `idbannhac` int NOT NULL AUTO_INCREMENT,
  `tenbannhac` varchar(100) NOT NULL,
  `theloai` varchar(50) DEFAULT NULL,
  `idnhacsi` int DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT (now()),
  PRIMARY KEY (`idbannhac`),
  KEY `idnhacsi` (`idnhacsi`),
  CONSTRAINT `bannhac_ibfk_1` FOREIGN KEY (`idnhacsi`) REFERENCES `nhacsi` (`idnhacsi`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Dumping data for table mymusic.bannhac: ~9 rows (approximately)
DELETE FROM `bannhac`;
INSERT INTO `bannhac` (`idbannhac`, `tenbannhac`, `theloai`, `idnhacsi`, `created_at`) VALUES
	(1, 'Du kích Sông Thao', NULL, 1, '2025-03-25 07:03:28'),
	(2, 'Trường Ca Sông Lô', NULL, 2, '2025-03-25 07:03:28'),
	(3, 'Tình Ca', NULL, 3, '2025-03-25 07:03:28'),
	(4, 'Xa khơi', NULL, 4, '2025-03-25 07:03:28'),
	(5, 'Việt Nam Quê Hương tôi', NULL, 1, '2025-03-25 07:03:28'),
	(7, 'Tiến về Hà Nội', NULL, 2, '2025-03-25 07:03:28'),
	(8, 'Nhạc rừng', NULL, 3, '2025-03-25 07:03:28'),
	(9, 'Tiếng hát giữa rừng Pắc Bó', NULL, 4, '2025-03-25 07:03:28'),
	(10, 'Thiên lý ơi', NULL, 4, '2025-03-25 07:03:28');

-- Dumping structure for table mymusic.banthuam
CREATE TABLE IF NOT EXISTS `banthuam` (
  `idbanthuam` int NOT NULL AUTO_INCREMENT,
  `idbannhac` int DEFAULT NULL,
  `idcasi` int DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT (now()),
  `ngaythuam` timestamp NULL DEFAULT NULL,
  `ngaysanxuat` timestamp NULL DEFAULT NULL,
  `thoiluong` time DEFAULT NULL,
  `file_path` varchar(50) DEFAULT NULL,
  `ghichu` text,
  PRIMARY KEY (`idbanthuam`),
  KEY `idbannhac` (`idbannhac`),
  KEY `idcasi` (`idcasi`),
  CONSTRAINT `banthuam_ibfk_1` FOREIGN KEY (`idbannhac`) REFERENCES `bannhac` (`idbannhac`),
  CONSTRAINT `banthuam_ibfk_2` FOREIGN KEY (`idcasi`) REFERENCES `casi` (`idcasi`)
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Dumping data for table mymusic.banthuam: ~5 rows (approximately)
DELETE FROM `banthuam`;
INSERT INTO `banthuam` (`idbanthuam`, `idbannhac`, `idcasi`, `created_at`, `ngaythuam`, `ngaysanxuat`, `thoiluong`, `file_path`, `ghichu`) VALUES
	(2, 2, 2, '2025-03-26 05:38:28', NULL, NULL, NULL, NULL, NULL),
	(3, 3, 1, '2025-03-26 05:38:28', NULL, NULL, NULL, NULL, NULL),
	(4, 4, 3, '2025-03-26 05:38:28', NULL, NULL, NULL, NULL, NULL),
	(5, 5, 4, '2025-03-26 05:38:28', NULL, NULL, NULL, NULL, NULL),
	(13, 1, 5, '2025-03-26 14:37:47', '2025-03-25 17:00:00', NULL, '03:45:00', 'DuKichSongThaoDoNhuan.mp3', '');

-- Dumping structure for table mymusic.casi
CREATE TABLE IF NOT EXISTS `casi` (
  `idcasi` int NOT NULL AUTO_INCREMENT,
  `tencasi` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
  `Ngaysinh` date DEFAULT NULL,
  `Sunghiep` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci,
  `created_at` timestamp NULL DEFAULT (now()),
  `anhdaidien` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`idcasi`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Dumping data for table mymusic.casi: ~6 rows (approximately)
DELETE FROM `casi`;
INSERT INTO `casi` (`idcasi`, `tencasi`, `Ngaysinh`, `Sunghiep`, `created_at`, `anhdaidien`) VALUES
	(1, 'Trần Khánh', '1931-03-04', 'Trần Khánh là một ca sĩ nhạc đỏ và là một nghệ sĩ nhân dân người Việt Nam. ', '2025-03-25 06:56:53', NULL),
	(2, 'Lê Dung', '1951-06-05', 'Lê Thị Dung là một ca sĩ, giảng viên giọng soprano người Việt Nam và một trong số ít những ca sĩ opera danh tiếng nhất trong nước.', '2025-03-25 06:56:53', NULL),
	(3, 'Tân Nhàn', '1982-08-18', 'Tân Nhàn, sinh năm 1982 tại xã Khả Phong, huyện Kim Bảng, Hà Nam Ninh, là giảng viên thanh nhạc, ca sĩ nổi tiếng của dòng nhạc dân gian Việt Nam, được phong tặng Nghệ sĩ ưu tú năm 2023. Hiện cô là Trưởng khoa thanh nhạc của Học viện Âm nhạc Quốc gia Việt Nam.', '2025-03-25 06:56:53', NULL),
	(4, 'Quốc Hương', '1915-08-21', 'Quốc Hương tên thật là Nguyễn Quốc Hương, sinh ngày 21 tháng 8 năm 1915 tại làng Kiến Thái, xã Kim Chính, huyện Kim Sơn, tỉnh Ninh Bình. Năm 17 tuổi, ông bắt đầu lưu lạc vào Trung Kỳ, sau là Sài Gòn và từng làm nhiều công việc như công nhân xe lửa, thủy thủ, bốc vác...', '2025-03-25 06:56:53', NULL),
	(5, 'Doãn Tần', '1947-06-08', 'Doãn Tần tên khai sinh là Phan Doãn Tần, là một ca sĩ nhạc đỏ người Việt Nam, Đại tá Quân đội nhân dân Việt Nam. Ông được Nhà nước Việt Nam phong tặng danh hiệu Nghệ sĩ Nhân dân.', '2025-03-25 06:56:53', 'DoanTan.jpg'),
	(16, 'Jack', '1997-04-02', 'Ca sĩ được các bạn yêu thích.', '2025-03-25 06:56:53', NULL);

-- Dumping structure for table mymusic.favorites
CREATE TABLE IF NOT EXISTS `favorites` (
  `id` int NOT NULL AUTO_INCREMENT,
  `idbanthuam` int DEFAULT NULL,
  `iduser` int DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idbanthuam` (`idbanthuam`),
  CONSTRAINT `favorites_ibfk_1` FOREIGN KEY (`idbanthuam`) REFERENCES `banthuam` (`idbanthuam`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Dumping data for table mymusic.favorites: ~0 rows (approximately)
DELETE FROM `favorites`;

-- Dumping structure for table mymusic.nhacsi
CREATE TABLE IF NOT EXISTS `nhacsi` (
  `idnhacsi` int NOT NULL AUTO_INCREMENT,
  `tennhacsi` varchar(100) NOT NULL,
  `ngaysinh` date DEFAULT NULL,
  `tieusu` text,
  `created_at` timestamp NULL DEFAULT (now()),
  `Gioitinh` varchar(50) DEFAULT NULL,
  `Quequan` varchar(100) DEFAULT NULL,
  `avatar` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`idnhacsi`)
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Dumping data for table mymusic.nhacsi: ~6 rows (approximately)
DELETE FROM `nhacsi`;
INSERT INTO `nhacsi` (`idnhacsi`, `tennhacsi`, `ngaysinh`, `tieusu`, `created_at`, `Gioitinh`, `Quequan`, `avatar`) VALUES
	(1, 'Đỗ Nhuận', '1922-12-10', 'Đỗ Nhuận là một nhạc sĩ Việt Nam. Ông là Tổng thư ký đầu tiên của Hội nhạc sĩ Việt Nam khóa I và II từ 1958 đến 1983, một trong những nhạc sĩ tiên phong của âm nhạc cách mạng.', '2025-03-25 06:55:58', NULL, NULL, NULL),
	(2, 'Văn Cao', '1923-11-15', 'Văn Cao là một người đồng nghiệp và là một người bạn tri kỉ của cố nhạc sĩ Phạm Duy. Văn Cao là một nhạc sĩ, họa sĩ, nhà thơ, chiến sĩ biệt động ái quốc người Việt Nam.', '2025-03-25 06:55:58', 'Nam', '', 'images/artists/1743294483_vancao.jpg'),
	(3, 'Hoàng Việt', '1928-02-28', 'Tên thật là Lê Chí Trực. Ông là một trong những nhạc sĩ đáng chú ý trong giai đoạn chiến tranh Việt Nam với nhiều tác phẩm nổi tiếng được sáng tác như "Tình ca", "Nhạc rừng", "Lên ngàn", "Lá xanh", "Quê hương".', '2025-03-25 06:55:58', NULL, NULL, NULL),
	(4, 'Nguyễn Tài Tuệ', '1936-05-15', 'Nhạc sĩ Nguyễn Tài Tuệ sinh ngày 15 tháng 5 năm 1936 tại xã Đại Đồng, huyện Thanh Chương, tỉnh Nghệ An.[4] Ông đến với âm nhạc từ niềm say mê thời tuổi thơ.', '2025-03-25 06:55:58', NULL, NULL, NULL),
	(14, 'Jack', '2121-03-02', NULL, '2025-03-25 06:55:58', NULL, NULL, NULL),
	(15, 'Trần Tiến', '1947-12-05', 'Trần Tiến là một nhạc sĩ, ca sĩ nổi tiếng của Việt Nam, được biết đến với nhiều ca khúc mang âm hưởng dân gian và nhạc hiện đại. Ông cũng nổi bật ở vai trò thủ lĩnh của nhóm nhạc Trần Tiến, với những tác phẩm được yêu thích qua nhiều thế hệ.', '2025-03-29 17:41:17', 'Nam', '', 'images/artists/1743270077.042038_TranTien.jpg');

/*!40103 SET TIME_ZONE=IFNULL(@OLD_TIME_ZONE, 'system') */;
/*!40101 SET SQL_MODE=IFNULL(@OLD_SQL_MODE, '') */;
/*!40014 SET FOREIGN_KEY_CHECKS=IFNULL(@OLD_FOREIGN_KEY_CHECKS, 1) */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40111 SET SQL_NOTES=IFNULL(@OLD_SQL_NOTES, 1) */;
