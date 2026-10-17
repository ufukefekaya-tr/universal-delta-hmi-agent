# Yeni proje başlatma

[START_NEW_PROJECT](../prompts/START_NEW_PROJECT.md) yeniden kullanılabilir görev promptudur. Genel core'a müşteri/makine adı eklenmez. Yerel proje `projects/<neutral-id>/` altında tutulur; input dosyaları immutable, output dosyaları yeni/sürümlü olur.

SDK 2.3.0 stdio/dokuz tool, inspect, common IR/validation ve conceptual preview uygulanmıştır. Yeni bounded layout yolu operations atlanır/null olduğunda source-local button/numeric/text/indicator/goto donor'ları, boş inert page donor, qualified rename/reorder ve visual scalar mapping kullanır; bounded service contract/full-suite bağımsız [layout milestone](../reports/NATIVE_LAYOUT_MILESTONE.json)/[review](../reports/NATIVE_LAYOUT_REVIEW.md) ile OFFLINE_PASS'tır; güncel Windows fresh clone OFFLINE_PASS; bağımsız ortam denetimi PASS; manifest hash eşitliği ve scoped proof commit kapanışı Git/checkpoint üzerinden doğrulanır. Macro donor SHA, typed internal binding, exact owner/trigger ve raw schedule ayrı qualified mapping ister; default registry genel macro şablonu vermez. Global Alarm low-level parser/mutator public Alarm IR/views/history trigger compiler değildir. Önceki [macro/Alarm milestone](../reports/NATIVE_MACRO_ALARM_MILESTONE.json)/[review](../reports/NATIVE_MACRO_ALARM_REVIEW.md) ve 225-test/c25 fresh clone tarihsel kabulüdür; yeni layout kaynağının Windows fresh clone sonucu [PORTABILITY](PORTABILITY.md) ile bağlıdır. Public save_as SYNTHETIC/0.0 ile sınırlı; gerçek production qualified flag olsa da kapalıdır. Units/native captions, native font units/picture/gradient/transparency, `Order` layer, Alarm views/history, external driver ve vendor/panel kabulü açıktır. Yeni proje veya insan onayı production yeteneği oluşturmaz.

## Minimum girdiler

| Girdi | Doğrulama |
|---|---|
| HMI target | Exact model, editor build, `.dps` veya `.dpa`, resolution ve driver. Kaynak profile/fixture veya insan kanıtı; model adından varsayım yok. |
| Native source | Yerel path, izin/provenance ve SHA-256. Kaynak salt okunur; tek source SHA. |
| İşlev sözleşmesi | Ekran/nesne listesi, operatör görevleri, read/write tip/adres/width/scale/unit ve davranış. |
| State/quality | Gerçek feedback kaynağı, komut kaynağı, stale/unknown/communication-loss davranışı. |
| Tasarım | Dil, operatör mesafesi, ekran hiyerarşisi, alarm/normal/disabled ayrımı, yazı/font/renk sahipleri. |
| Scope | Exact allowed_write/protected, baseline, policy epoch, authority, tek dosya owner ve commit owner. |
| İnsan kabulü | Sürümlü preview tasarım onayı; sonra insan IDE/panel kanıtı. |

Kaynakta bulunabilen model/driver bilgisini tekrar kullanıcıya sorma. Kritik bilgi bulunamıyorsa bağımsız read-only araştırmaya devam et ve yalnız karar isteyen eksik girdiyi belirt. Mevcut V1 qualification pilot modelleri DOP-B07S411 ve DOP-110IS root tarafından seçilmiştir; bu seçim yeni müşteri projesinin hedefini otomatik belirlemez.

Bounded layout contract'inde her mevcut page ID bir kez, boyutları kaynakla aynı; yeni page için exact `screen_donor` nesnesiz ve executable/scheduled macro taşımayan inert kaynak olmalıdır. Yeni donor plain page baseline'ı yalnız VER=16, ID, framed wTextLen, DocSizeX/Y ve PanelSizeX/Y yedi alanıdır; extra/unknown/background/lock/page-macro inheritance kabul edilmez. Immediate empty Aux ve known extents gerekir; saved yeni page fingerprint'i immutable donor ile eşleşir. Public layout guard bütün Screen/Element/State `Order` alanlarını 0/no-op/append-only dahil reddeder. Nesne kind/Type/SubType, state values ve read/write metadata source-local donor'a bağlıdır. Caption text, boş değer dahil, açık intent taşır; numeric donor'un unmanaged yazısı devralınmaz. Explicit State text ayrı unit/caption-object desteği değildir. Rename/reorder tam ID listesi ve qualified structural mapping; goto için target ID/name companions ve izinli encoding gerekir.

Font isteği yalnız State.FontSize0, FontRatio0=100, ASCII FontName0 ve scale=1 contract'iyle uygulanır; points/pixels eşitliği varsayılmaz. Renk `rgb24` veya ayrı calibrated `colorref24` encoding'ini açık seçer. State-only fill dahil field/scope/range ve bütün appearance companion baseline'ları belirtilir; Font/Picture/PIB/opacity/shadow/gradient substrings kind-prefix altında saklanamaz, unknown visual key exemption vermez. PictureOffset/PIB Name/Picture Name donor flat-style için kullanılamaz. Registry empty-companion contract'ini vendor donor'a taşıma. Bunlar native font/glyph veya piksel görünümü onayı sağlamaz; fonksiyonel guard düzeltmelerinin bağımsız reviewer tekrar kabulü bounded OFFLINE_PASS'tır.

Explicit operations da public IR intent gate'inden geçer: fixed represented property field/owner, açık scalar/state intent ve primary language=0 caption gerekir. Qualified extra native property public güç eklemez; low-level primitive ayrı contract'tir. Goto kind tam canonical Type+SubType ve navigation.match taşır; varsa ASCII name companion final/no-op'ta da eşleşir. Native state_fill metadata şekli typed doğrulanır. Saved candidate semantic check sonrası apply receipt SHA'sına bağlıdır; opaque corruption yeni output oluşturmaz. Bounded bağımsız offline kabulünü selected-model/native-visual feature kabulüne genişletme; Windows fresh clone OFFLINE_PASS; bağımsız ortam denetimi PASS; manifest hash eşitliği ve scoped proof commit kapanışı Git/checkpoint üzerinden doğrulanır.

V1 test registry ID'leri `dop_b07s411_dopsoft2` ve `dop_110is_diascreen`'dir. Bu test hedeflerini yeniden seçtirme; mevcut fixture/build/driver kalibrasyon eksiklerini ve emitter geliştirmesini açık iş olarak kaydet. Common IR/synthetic preview iki gerçek native pilotun yerine geçmez.

## Yerel dosya düzeni

```text
projects/<neutral-id>/
  inputs/          # immutable native input, license/provenance references
  contracts/       # target, design, tags, behavior
  reviews/         # independent technical + ordered aesthetic reports
  approvals/       # human approval bound to hashes
  outputs/v001/    # new files only, native/conceptual labels
  evidence/       # offline, human vendor, human physical cards
  handoff/        # open acceptance and human steps
```

Templates çalışma biçimini gösterir; doğrudan çalışabilir vendor projesi değildir. Placeholder, qualified metadata veya insan onayı mevcut kapalı production emitter'ı açmaz. Task envelope/checkpoint `.agent-state/<task-id>/` altında orkestratörce tutulur. Template'in profile/contract key'leri native field isimleri değildir; gelecekte geliştirilmiş emitter ve kanıtlı schema üzerinden dönüştürülür. Şimdi teslim edilebilen conceptual artifacts ile bekleyen production native artifacts açık ayrılır.

[WORKFLOW](WORKFLOW.md) W0–W10 kapılarını uygula. Yeni proje yaratmak; GUI, derleme, bağlantı, download, force veya remote/push yetkisi vermez. Kabul ölçütü [GOALS](GOALS.md) ile açık adlandırılır.
