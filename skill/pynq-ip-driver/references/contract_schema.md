# Contract schema

Required: `name`, `base_address`, `address_range`, and `registers`. Each register has `name`, byte `offset`, `width` in 8/16/32/64, and access `ro`/`rw`/`wo`. Optional `control_protocol`, `endianness`, tensor/buffer descriptions, timeout, completion rule, and `unverified_semantics` must be explicit. HWH can corroborate address data but cannot prove algorithm meaning.
