# Mevcut kaynak grafiği ve inert silme

Gözlem: ön WIP, Recipe boş CRLF satırını unknown graph sayarak gerçek kaynağı reddetti. Salt flag/hash değiştiren profile kabulü güvenli çözüm değildi. Ayrı graph schema, primary reader/writer kanıtı ve immutable source extent doğrulaması gerekti.

Karşı inceleme; tekrar eden SubMacro alanını, TagLinkCount/LinkSize tutarsızlığını, eksik recipe/history kayıtlarını ve ham Unicode exception'ını yakaladı. Gerçek `SubMacro%03dLen` anahtarı ters isimle uydurulamaz; password scalar'ı primary `%s` yapılandırmasından ayrı owner-ref kabulü üretmez. Bu source subset'i macro body kayıtlarını reddeder.

Minimum değişiklik: exact source-pinned inert owner silme, tüm survivor byte'larının korunması, emitter'dan ayrı IR/source range subtraction, whole-body restoration. Genel layout bypass veya kimlik yeniden numaralama yoktur. Görsel/font/numeric/quality feature'larının hazır olduğu çıkarılmaz.

Helper'ın freshness kontrolünde kaynak/registry kaybolunca raw OSError sızması ayrıca bulundu. Dört gerçek cleanup regresyonu, kaybolma ve PermissionError durumlarında typed `CALIBRATION_CHANGED`, destination yokluğu ve temporary-file temizliğini doğrular. Bir checksum kontrolü, okunabilirlik ve işlem sırası kontrollerinin yerine geçmez.

Rollback: kaynak hiç değişmediği için yeni candidate kullanılmaz; önceki kaynak ve hash'ler geçerlidir. Yeni kaynak/vendor resave ayrı calibration ve onay ister. Ders başka model/driver/macro/alarm veya native-render acceptance'ına genellenmez.
