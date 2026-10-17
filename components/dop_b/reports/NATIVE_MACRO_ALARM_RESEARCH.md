# Sonraki native aşama için salt-okunur kalibrasyon

Araştırmacı `/root/native_macros_research` ve ayrı alarm framing denetmeni, mevcut source dosyalarını değiştirmeden inceleme yaptı. GUI/IDE/PLC/panel kullanılmadı; vendor payload, varlık veya üçüncü taraf uygulama kodu repoya taşınmadı. Aşağıdaki çalışma araştırma deneyidir; public MCP veya tamamlanmış emitter desteği değildir.

## Kaynaklar ve kapsam

| Kaynak | SHA-256 |
|---|---|
| DIAScreen Full Element Demo | `fc079f74ed9b34e2e698b0c65c95c4f914983594f658cadc72e1ee4d97493ed5` |
| DIAScreen Alarm function EN | `ae60464b551a5f773871910c180ccd72fdc63dc5123a76a17c16ab50bd94b8be` |
| DIAScreen History function | `7f35b5fd05537106b46a9791a426a1b3e3a59f8afa1f870595e9c0fd75e24471` |
| Public DOP-B03E211 | `07d90a3900cb86e994b55a467f594809e4ffe1e0681f329d205ff26b3b688f90` |
| HMC N411; B kabulü değildir | `4c21c3f04484f620c48cf4aae101d7b2d3288a1dc11455330b20cc53fd67d148` |
| HMC N500; B kabulü değildir | `a724e5d4af44ce7cd95ad6674a860939ae0940dfab20af9844449bcfa4e82a33` |

Public B kaynağı [yazarın sabit commit'indedir](https://raw.githubusercontent.com/ismaelfari1996/hmi-simulacion-dosificador/aa8684c51dcd4372d6dc7d274d7cf7a51a7d94d1/Dosificador.dps). Lisans/provenance ve farklı-model sınırı [milestone kaydında](NATIVE_EMITTER_MILESTONE.json) bulunur. Private vendor kurulum yolları kalibrasyon verisi veya runtime gereksinimi olarak saklanmaz.

## Makro sahipliği ve satırlar

| Sahip | Gözlenen exact alanlar |
|---|---|
| Application | InitialMacroLen, BackgroundMacroLen, ClockMacroLen |
| Screen | OpenMacroLen, CloseMacroLen, CycleMacroLen |
| Element | BeforeExecMacroLen, AfterExecMacroLen; belirli butonlarda ButtonOnMacroLen, ButtonOffMacroLen |

ClockMacroDelayTime, ClockMacroPriority, LineBrkBackgndMacro değerleri örneklerde 100/0/1 idi; zaman birimi, izinli aralık ve scheduling semantiği kalibre edilmedi. Bu değerler evrensel default yapılmaz.

22 DIAScreen dosyasında 123 nonempty program / 986 satır; public B eklenince 125 program / 1.223 satır görüldü. Bu corpus önceki 1.921-program kümesiyle örtüşür; toplam alınmaz. Direct internal adres kalıplarında source metni ile bütün operand string'leri karşılaştırıldı:

| İşlem kalıbı | Descriptor hex | Tutarlı eşleşme |
|---|---|---:|
| Assignment | 2507031e | 414 |
| Addition | 240f0700 | 75 |
| BITON | 0a00011b | 10 |
| BITOFF | 0a00011c | 24 |
| Word IF == | 140e0348 | 61 |

584 eşleşme source/operand yapısı bakımından tutarlıydı. IF >= `140e034b`, IF < `140e034c`, ELSE `0000005c`, ENDIF `0000005d` ayrıca gözlendi; execution kabulü değildir. In-memory synchronized tek operand değişikliği descriptor, flags ve unused operand'ları koruyarak yeniden okundu.

HMC paired örneklerinde assignment/addition flags byte 4–7 little-endian DWORD=1 `(DW)` ile; byte 8–11 DWORD=1 signed annotation ile ilişkiliydi. Signed byte 5 değildir. İlk dört byte ve same-opcode flag farklılıkları opaque kalır; bütün donor flag tuple korunur. Width/signedness source yazısını değiştirerek dönüştürülmez. HMC korelasyonu DOP-B qualification yaratmaz.

Dört whole-file araştırma denemesinde yalnız belirtilen macro record'un literal/source/operand/length değişti; diğer records, prefix, thumbnail, resource tail, descriptor/flags ve addressing korundu. Source değişmedi; 4/4 yeniden okuma/preservation PASS:

| Owner | Candidate SHA-256 |
|---|---|
| DIA Application InitialMacroLen | `17501a47ab6a9e61358b9383c0a287c7c604199b6a49f18f70abd28776df81c7` |
| DIA Application ClockMacroLen | `4adc34e71562c0acb385c840131451d4fe1c847d0349c489c9a1605b0904a426` |
| DIA Element BeforeExecMacroLen | `172c54664a152117617eabc7ff4fb3f2c96dd06a342830115bb8d6390b20d357` |
| B Application InitialMacroLen literal | `cae8577a9ac0db60bfe7756478515a720e9b1e1d551ff74e6c7de5ac8b2cbd69` |

B source alias kullanır, operands resolved internal adres taşır. B denemesi yalnız literal değiştirdi; alias/address resolver geliştirilmedi. Nonempty B clock donor bulunmadı. External/DIA_TAG yazma kalibrasyonu yok.

Sonraki uygulama exact owner/field/program SHA/line index/line SHA ve source-local calibrated donor ister. Source ile ilgili operands birlikte yazılmalı; unused strings, descriptor ve flags korunmalı. Alias, unqualified adres/width/owner değişimi reddedilmeli; IF yapısı doğrulanmalı. Framing PASS semantik PASS değildir.

## Alarm resource sınırı

Bağımsız bounded walker SubMacro → Global_Auxkey → Alarm → History sınırlarını yalnız record boundary'de izledi; framed string/binary uzunluklarını atladı. 22 DIAScreen örneğinin tamamında traversal geçti. Dört detailed holdout byte-exact reserialize geçti:

| Kaynak | Alarm records / bytes |
|---|---:|
| Alarm function EN | 112 / 2.740 |
| History function | 40 / 674 |
| Full Element Demo | 131.099 / 2.944.600 |
| Public B | 130 / 2.847 |

On malformed varyant reddedildi: negative/overflow length, kalan byte sınırını aşma, odd UTF-16 length, eksik NUL/CRLF, truncation, beklenmeyen section, duplicate Alarm ve invalid surrogate. Properly framed macro içine yerleştirilen sahte Alarm/History başlıkları atlandı; substring search yanlış başlığı seçti. Bilinmeyen preceding section/framing'de durulmalı, observed offset gömülmemeli.

Alarm definitions global kaynaktır; son ekran veya bir view nesnesinin parçası değildir. Capacity, serialized entries ve enabled entries ayrılır; sıra ve repeated alan sahipliği korunur. Exact gözlenen spellings: `AlarmTriggerFmt001`, `AlarmTriggerIntNum001`, `AlarmTriggerDotNum001`, `AlarmTriggerCount001`, `AlarmTriggerOperator001-001`, `AlarmTriggerMax001-001`, `AlarmTriggerMin001-001`, `WatchAddr001-001`, `WatchAddrVarFmt001-001`, `WatchAddrReadLen001-001`, `WatchAddrMenFmt001-001`. Sonuncu alanın native yazımı MenFmt'dir.

Type11/SubType1 alarm history, SubType2 active alarm, SubType3 frequency, SubType4 moving strip iki bağımsız DIA örneğinde ilişkilendirildi. 22 örnekte 16 view vardı; mevcut FunctionKeyPartID değerleri -1 idi. Positive dependency graph kalibre edilmedi. Public B alarm definitions içerir fakat Type11 view donor içermez.

**Temel alarm geçmişi `[Alarm]` retention ve alarm-history view ile ilgilidir. `[History]` process-data sampling ayrı ileri kapsamdır ve korunur.** Acknowledgement, history persistence, external adresler, exact selected-model native üretim ve insan vendor/panel kabulü hâlâ açıktır.
