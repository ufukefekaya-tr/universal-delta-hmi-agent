# Opak DIAScreen prefix'i: dar koruma sözleşmesi

**Gözlem:** Gerçek DIAScreen manufacturer örneği mevcut literal parser'a sığmasına rağmen prefix doğrulamasında reddedildi. Sekiz ek global bölüm ve üç bölümde nonempty unkeyed kayıt bulunuyordu.

**Kök neden:** Eski kapı bilinen global anahtar biçimlerini zorunlu tutuyordu. Dosyayı okumak, bütün opak alanları değiştirme yetkisi anlamına gelmez.

**Karşı görüş:** İsimleri whitelist'e eklemek yeterli değildir. Lua/Ethernet kayıtlarının semantiği, bölüm sırası, byte extent'leri ve diğer alanların korunması kanıtlanmadan genel mutator açılması veri kaybını gizleyebilir.

**Minimum değişiklik:** Ayrı V2/source-local DIAScreen prefix politikası; exact family/model/serialized/canvas, sabit bölüm sırası ve tam prefix hash'i. Yalnız kaynak inert primary caption ve Element geometri kayıtları, her biri aynı extent'te. Native ve public katmanda ayrı whole-BODY oracle. Eski V1/default ve başka compiler modları genişletilmez.

**Tekrar test:** Karışık/no-op şema; wrong family/model/version/canvas; yanlış op/arg/state/property; ilgisiz alan veya owner sıra bozulması; stale source/prefix/owner/onay; aktif visibility; uzunluk telafisi; kaydedilmiş gerçek holdout/replay/geri dönüş. Exact sonuçlar milestone ve güncel test raporundadır; test planı PASS hükmü değildir.

**Geri dönüş:** Kaynak değişmez. Sözleşme ve yeni çıktı görev-local kalır; yeni profile registry kullanılmadan eski yollar aynı kapıda kalır. Aday iptal edilirken korunan orijinal kaynak kullanılabilir.

**Genellenebilirlik sınırı:** Aynı model adı veya suffix yeterli değildir. Kalibrasyon freshness/tutarlılık kanıtıdır; manufacturer provenance, lisans, native görünüm, vendor/runtime veya bütün aile desteğini ispatlamaz. Lisanslı örnekler genel repo veya portable pakete taşınmaz.
