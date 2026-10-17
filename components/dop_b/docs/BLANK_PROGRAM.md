# Boş hedef ve ayrı kontrol kütüphanesi

`blank_program` yeni, dosya odaklı üretim modudur. Gerçek boş hedef projeye yalnız onaylı tasarımın yeni kontrollerini yerleştirir. Altı vendor referans nesnesi ayrı, değişmez bir kütüphanede kalır; aday dosyaya taşınmaz. Önceki `control_generation` ekleme modu aynen korunur.

## Girdiler ve kaynak sözleşmesi

İlgili proje workspace'inde gerçek sıfır-owner hedef, aynı model/sürümden türetilmiş altı donor'lu kaynak, altı property görüntüsü ve source-local kontrol profili bulunur. Hedef ve kütüphanenin global bölümleri, sayfa kimlikleri/sırası, başlıkları, Aux ve ilk37 prefix byte'ı karşılaştırılır. Application.Name/MeMeCode kayıt farkları yalnız gözlenen save metadata'sı olarak kabul edilir; çıktı her zaman hedefin kendi global verisini kullanır. Değişmiş haberleşme yapılandırması veya farklı model bu eşleşmeyi geçmez.

Kütüphane tam altı kalibre edilmiş owner içerir: set-on, set-off, momentary, maintained, UINT input ve UINT display. Yedinci veya eşlenmemiş nesne kabul edilmez. Donor kimlikleri rezervdir; yeni native kimlikler proje genelinde benzersiz olmalıdır. Hedefte eski nesne varsa onu sessiz silmek yerine `NONEMPTY_PROGRAM_TARGET` hatası verilir.

Her yardımcı profil, normal registry profiliyle aynı typed alan denetiminden geçer. Eksik/yanlış tipte id, model, family, serialized sürüm, resolution, capabilities veya native_schema ham exception oluşturmaz; oturum açılmadan ve calibration çıktısı yazılmadan reddedilir. Kütüphane/profil/calibration ve bütün property görüntüleri SHA ve byte boyutuyla bağlanır; plan, validate, apply ve kayıt öncesi yeniden kontrol edilir.

## Taşınabilir hazırlık

Komutlar checkout'a kurulmuş Python ile çalışır. Bütün veri argümanları seçilen workspace'e göre relative'dir; vendor kurulumuna veya eski bilgisayar yoluna bağımlılık yoktur.

```text
python scripts/calibrate_controls.py --workspace "projects/<project>" --source "library/controls.dps" --family delta_dopsoft2 --witnesses "evidence/properties.json" --output-dir "contracts/controls-v001" --review-reference "reviews/control-library.md"
python scripts/calibrate_program.py --workspace "projects/<project>" --target "inputs/blank.dps" --library "library/controls.dps" --library-profile "contracts/controls-v001/profiles/source_controls_v1.json" --output-dir "contracts/program-v001" --source-reference "inputs/PROVENANCE.md" --review-reference "reviews/blank-lineage.md"
python -m universal_hmi.cli --profiles "projects/<project>/contracts/program-v001/profiles" serve --workspace "projects/<project>"
```

İkinci komut yalnız `program_calibration.json` ve `profiles/blank_program_v1.json` üretir; native dosya veya insan tasarım onayı üretmez. Mevcut çıktının üzerine yazılmaz. `.dpa` için ayrı DIAScreen family/profile, gerçekten eşleşen iki kaynak ve aynı inceleme gerekir; `.dps` uzantısını değiştirmek dönüşüm değildir.

## Dokuz araçla üretim

`open_project` için profile_id `blank_program_v1`, source_path gerçek boş hedeftir. `inspect` boş hedefi gösterir. `plan_changes` mevcut hedef sayfalarının tamamını ve yalnız yeni kontrolleri içeren IR alır; `native_preserved` donor nesneleri tasarıma eklenmez. operations omitted/null bırakıldığında source-qualified donor klonlama, geometry, exact binding ve state işlemleri türetilir. Açık operasyon listesinin de aynı niyetle eşleşmesi gerekir.

`preview` kavramsal IR gösterir; native font, resim, katman veya panel görünümü değildir. Kullanıcı makine projesinde teknik ve sıralı iki estetik inceleme, sürüme/hash'e bağlı gerçek insan tasarım onayı gerekir. Tarafsız adaptör test yetkisi makine onayına dönüşmez. `validate` bulguları kapanınca `apply_plan`, yeni-only `save_as` ve `diff` kullanılır.

Native derleyici kontrolleri geçici donor bağlamında doğrular, yalnız yeni owner extent'lerini boş hedefe yerleştirir. Servis ayrı IR→ham gövde beklentisi üretir; native operation emitter'ının çıktısını kendi kabul oracle'ı olarak kullanmaz. Kaydedilen aday yeniden açılır ve bütün beklenen gövdeyle karşılaştırılır. Boş IR, boş hedefin bütün dosya byte'larını aynen üretir.

## Dosya koruması ve açık kapsam

Hedefin thumbnail, ilk37 prefix byte'ı, globals, mevcut sayfa başlığı/Aux ve opak kaynakları korunur. Bilinen son DWORD gerçek decoded body uzunluğuna güncellenir. Yalnız tam framing ile sahibi belirlenen boş `[Tag]` kaynağında, vendor blank→controls kaydında görülen `TagLinkCount=0` → `TagLinkCount=1 / LinkSize=0` geçişi yapılır. Resim/SRAM/tag/wide/macro payload içindeki header benzeri byte'lar bölüm sahibi sayılmaz; substring araması yazma yetkisi vermez. Diğer tail verisi exact kalır.

Çıktı kapsamı **BLANK_TARGET_SOURCE_LIBRARY_CONTROLS / OFFLINE_NATIVE_CANDIDATE**'dır. İlk kontrol kütüphanesi yakalanmış M0 BOOL ve D0 UINT ile sınırlıdır; isteğe bağlı [kaynak sürücüsü adres sözleşmesi](DRIVER_ADDRESSES.md) ayrı M/S/D adreslerini kütüphane ve boş hedef yolunda açar. Identity scale, UINT sıfır ondalık ve R=B renk sınırları korunur. Yeni sayfa/gezinti, göstergeler, signed/decimal tipler, makro, alarm/history, tam stil/katman ve iki gerçek profilin ortak pilotu henüz tamamlanmadı. `program_writer_complete=false`; opaque graph, native pixels, vendor compile/simulation ve fiziksel kabul açık kalır. Temiz nesne envanteri tek başına panele yükleme kabulü değildir.

[Gerçek kaynak deneyi](../reports/BLANK_PROGRAM_GENUINE_PROBE.json), [milestone](../reports/BLANK_PROGRAM_MILESTONE.json), [bağımsız inceleme](../reports/BLANK_PROGRAM_REVIEW.md).

Bu belgedeki `blank_program` kapsamı önceki altı-control modudur. Yeni sayfa/metin/indicator/goto için ayrı [üç kaynaklı multipage sözleşmesi](MULTIPAGE_PROGRAM.md) gerekir; eski library/source-profile flag'i genişletilmez. Sadece onun gerçek B10 kaynaklarıyla doğrulanmış stored-layout kapsamı açılmıştır; diğer native veri türü, tam görünüm, quality, macro/alarm ve vendor/panel kabulü hâlâ açıktır.
