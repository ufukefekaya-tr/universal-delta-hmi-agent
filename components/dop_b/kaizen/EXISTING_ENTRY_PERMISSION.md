# Giriş iznini komut görevinden ayırma

Gözlem: aynı SetOn tipi START veya STOP taşıyabilir. Tipten interlock üretmek STOP'u engelleyebilir. Numeric giriş izni commit anındaki kontrolün kanıtı değildir.

Kök neden: native özellik, proje komut semantiği ve runtime kalite/zaman garantisinin tek yetki sayılması. Textual link adı ile native index farklı kimliklerdir.

Karşı görüş: bütün butonlara BOOL izni eklemek kolaydır; bırakma/STOP/safety ve stale iletişim güvenceye alınmaz. Sınıflandırma explicit insan proje kararıyla START veya F0 parameter girişiyle sınırlıdır.

Minimum değişiklik: source/owner/write binding/namespace raw pinlerini ayır; yalnız InterLockVar/Level yaz, original link'i koru. İşlemleri original source üzerinde doğrula, complete BODY oracle'ıyla karşılaştır.

Tekrar test: rehashed STOP/binding/namespace, octal X8/yanlış istasyon/link/WORD izin, raw girdi drift/postlink race, eski onay, bozuk emitter, no-op/replay. Sentetik test vendor/runtime kabulü değildir.

Rollback: source değişmez; aday kaldırılıp original/pinlerle eski plain/numeric profil kullanılabilir. Başka model/editor/driver/action'a genellenmez. Kalite/maximum-age/AND/commit-time açıktır.
