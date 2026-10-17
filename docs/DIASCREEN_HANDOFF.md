# Bağımsız DIAScreen teslim sözleşmesi

DIAScreen ajanına yeni `universal-diascreen-hmi-agent` reposunda çalışma görevi insan yetkisiyle gönderildi. Çatıya veya DOP-B deposuna yazmayacak. İlk inceleme bağımsız genel DIAScreen reposu bulunmadığını, lisansı belirtilmemiş upstream ile ayrı proje wrapper'larının kullanıldığını doğruladı.

Teslimde gerekenler:

- Özgün/proje agnostik kod; müşteri adı, tag/IP, logo, özel native dosya ve host yolu yok.
- stdio giriş noktası ve Python bağımlılıkları; önerilen modül `universal_diascreen_hmi.cli`.
- Bütün araç adları ve JSON şemaları; dokuz temel araç dışında kalan işlevler için de explicit harita.
- Kaynak/model/editor/driver family contract; unsupported alanlarda açık hata.
- Kaynak manifesti, hashli taşınabilir paket, commit/sürüm ve kurulum komutları.
- `FEATURE_MIGRATION.json` D01–D44, U01–U09 ve18dosya/4hariçGUI araç için yeni uygulama/test/durum eşleştirmesi.
- `REGRESSIONS.json` gerçek hata senaryolarının karşılığı.
- Bağımsız eksiksizlik denetimi; dokümantasyon satırı uygulama kanıtı sayılmaz.

N016 vendor modüllerini tek başına almak eski wrapper özelliklerini kaybettirir. Momentary/maintained tür sözlüğü eski upstream'den güvenle alınamaz. Macro görünür kaynak ile parsed operand ayrı tutulmalıdır. Geri alınmış heartbeat ve henüz üretilmemiş alarm history varsayılan özellik olarak açılamaz.

Bu bağımsız teslim gelene kadar çatı DIAScreen'i `UNAVAILABLE` gösterir. Kaynak DOP-B deposundaki dar DIAScreen deneyleri bu teslim yerine kullanılmaz.
