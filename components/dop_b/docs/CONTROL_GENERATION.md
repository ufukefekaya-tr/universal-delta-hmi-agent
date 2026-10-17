# Kaynakla kalibre edilmiş kontrol üretimi

Bu mod, vendor tarafından kaydedilmiş altı ayrı donor'dan dört buton türü ve UINT sayı girişi/göstergesi üretir. Gerçek dosya kaydı, MCP işlemleri ve yeniden okuma offline olarak doğrulanır. Tam makine programı ve vendor kabulü değildir.

## Taşınabilir girdiler

Her proje kendi workspace'ini kullanır. Kaynak `.dps/.dpa`, altı özellik görüntüsü ve kaynak incelemesi bu workspace'te kalır; genel repoya vendor varlıkları veya özel yollar eklenmez. Görüntünün dosya adı tür kanıtı değildir: bağımsız inceleme exact screen/element kimliğini, kaydedilmiş native türü ve görüntü SHA'sını eşler.

`properties.json` tam altı anahtar içerir: `set_on`, `set_off`, `momentary`, `maintained`, `numeric_input`, `numeric_display`. Her değer şu biçimdedir:

```json
{"screen_id":"1","element_id":"1","path":"evidence/set_on.jpg","sha256":"<exact-image-sha256>"}
```

PNG/JPEG görüntüleri en çok 10 MiB olabilir. Kaynak owner, model, serialized Version, global bölümler, sayfa başlığı/Aux ve bütün property görüntüleri SHA ile dondurulur. Üretici editörün executable sürümü ayrı kanıttır; klasör adı veya Application.Version onun yerine kullanılmaz.

```text
python scripts/calibrate_controls.py --workspace "projects/<project>" --source "inputs/controls.dps" --family delta_dopsoft2 --witnesses "evidence/properties.json" --output-dir "contracts/v001" --review-reference "reviews/source-controls.md"
python -m universal_hmi.cli --profiles "projects/<project>/contracts/v001/profiles" serve --workspace "projects/<project>"
```

İlk komut yalnız yeni calibration/profile JSON dosyaları üretir. Kaynak değişmez; çıktı üstüne yazılmaz. DIAScreen için family `delta_diascreen` seçilir; bu seçenek tek başına yeni model/özellik kabulü değildir.

## İzinli tanım

Profile ID `source_controls_v1` olur. Dokuz MCP aracı aynı kalır: `open_project`, `capabilities`, `inspect`, `plan_changes`, `preview`, `validate`, `apply_plan`, `save_as`, `diff`.

- Kaynağın bütün sayfaları ve owner'ları başta aynı sırada `native_preserved` olarak tanımlanır. Kimlik, geometri ve source owner SHA değişmez; bu nesneler gizlenemez veya silinemez.
- Yeni owner'lar existing sayfaya eklenir. `native_id` pozitif, proje genelinde yeni ve benzersizdir.
- Buton davranışı exact donor türüne bağlıdır. Set-on, set-off, momentary ve maintained birbirine dönüştürülmez. Native `Value=0/1` metinleri ayrı yazılır; komut isteği fiziksel feedback olarak sunulmaz.
- Kalibrasyonsuz adres genişletmesi kapalıdır. İlk profil yakalanmış `{Link…}<station>@M0` BOOL ve aynı prefix'teki `D0` UINT ile sınırlıdır. İsteğe bağlı [kaynak sürücüsü adres sözleşmesi](DRIVER_ADDRESSES.md), doğrulanmış Delta DVP profilinde ayrı M/S/D adreslerini açar. Link/memtype kayıtları exact donor'dan gelir; kanal adı ile native Link integer'ının aynı olduğu varsayılmaz.
- UINT 16-bit unsigned, identity scale, tam sayı ve uygun limitlerle temsil edilir. Display donor'unda bulunmayan MinValue/MaxValue alanları icat edilmez. TIME veya 64-bit fallback yoktur.
- Geometri, primary durum metni, FontSize0 ve byte sırası belirsizliğinden etkilenmeyen R=B renkler düzenlenebilir. Diğer font/gradient/image/opacity/Order/driver/tag/macro/alarm alanları korunur.

`plan_changes` için operations omitted/null bırakılır. Ortak geometri/tip/yetki kontrolleri ve bağımsız bütün-gövde beklenen değer denetimi geçmelidir. `preview` kavramsal IR'dır; source owner'ları native çizim gibi göstermez. Kullanıcının makine adayı için sürüme bağlı teknik, sıralı estetik ve insan onayı zorunludur. Neutral geliştirme örneği yetkisi üretim tasarımı onayı olarak aktarılmaz.

`save_as` yeni dosyayı yeniden okur. İlk 37 zarf byte'ı, thumbnail, globals, orijinal sayfa/Aux, orijinal owner'lar ve tail byte'ları değişmez. Kaynakta doğrulanmış decoded prefix son DWORD'u gövde uzunluğudur: XOR 0x64 ardından little-endian uint32. Gövde büyüdüğünde bu alan güncellenir; boyutu tutmayan control source/candidate reddedilir. Bilinmeyen prefix biçimi bu kuralı otomatik kazanmaz.

## Teslim sınırı ve sıradaki iş

Temiz kontrol ekranı için ayrı [blank_program](BLANK_PROGRAM.md) modu eklenmiştir: source-qualified donor kütüphanesi çıktıya taşınmadan gerçek boş hedefe yeni kontroller yerleştirilir. Bu belgedeki append modu ve original-owner koruma kuralı değişmemiştir.

Sonuç `OFFLINE_NATIVE_CANDIDATE / APPEND_SOURCE_CALIBRATED_CONTROLS`, `program_writer_complete=false`, native visual/vendor/simulation/physical `NOT_RUN` olarak kaydedilir. Kaynakta unbound referans nesneleri varsa aynen kalırlar; bu aday panele yüklenmeye hazır diye verilmez. Temiz program üretimi, referans owner'ların açık planla kaldırılması/değiştirilmesi, adres namespace'i, yeni sayfa/gezinti, makro ve alarm kapsamının tamamlanmasını bekler. [Güncel kanıt](../reports/CONTROL_GENERATION_MILESTONE.json), [bağımsız inceleme](../reports/CONTROL_GENERATION_REVIEW.md).
