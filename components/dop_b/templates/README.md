# Proje-local şablonlar

JSON dosyaları örnektir; placeholder/`UNVERIFIED` üretim gate'ini açmaz. Alan adları vendor native alanları değildir. Exact native dönüşüm yalnız qualified profile schema'sına bağlıdır. Şablonu `projects/<neutral-id>/contracts|approvals|evidence|reviews/` ignored alana kopyala; özel dosyayı core'a taşıma.

| Şablon | Amaç |
|---|---|
| [TARGET_PROFILE](TARGET_PROFILE.json) | Exact model/editor/format/resolution/driver, schema/fixture qualification |
| [DESIGN_BRIEF](DESIGN_BRIEF.json) | Shared conceptual design model; runtime şema ayrı doğrulanır |
| [TAG_BINDINGS](TAG_BINDINGS.json) | Source/read/write/type/address/width/behavior contract |
| [HUMAN_APPROVAL](HUMAN_APPROVAL.json) | İnsan preview version ve contract hash onayı |
| [VENDOR_EVIDENCE](VENDOR_EVIDENCE.json) | İnsan IDE open/compile/simulate kanıtı |
| [PHYSICAL_EVIDENCE](PHYSICAL_EVIDENCE.json) | İnsan panel/PLC senaryo kanıtı |
| [REVIEW_CHAIN](REVIEW_CHAIN.json) | Teknik ve sıralı estetik review; bir odaklı aesthetic repair |
| [TASK_ENVELOPE](TASK_ENVELOPE.json) | Immutable baseline/epoch/authority/exact scope ve owner |
| [SESSION_CHECKPOINT](SESSION_CHECKPOINT.json) | Tek orkestratörün raw envelope hash/current HEAD/sequence kaydı |

`null` eksik anlamındadır; 0/false/boş PASS yerine kullanma. SHA alanları gerçek raw bytes üzerinden hesaplanır. Görev runtime artifacts `.agent-state/<task-id>/` altında tutulur; guard task_id, full baseline commit, current HEAD, policy epoch ve raw envelope SHA'yı doğrular. Owner isimleri görev zarfında açık atanır; template isimleri hesap/yetki oluşturmaz.

Evidence key profile+feature+scenario+artifact SHA+test revision'dır. Compile/simulate veya physical steps ajan tarafından tamamlandı gösterilemez. Onay değişen source/profile/design/binding/behavior/preview'a taşınamaz. Synthetic/kavramsal render native üretim onayı değildir.
