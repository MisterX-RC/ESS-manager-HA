# Prices

The grid transport tariff and prices including taxes - what the plans count with when they buy and sell.

[← Back to the README](../README.md)

## Grid transport tariff

In the Netherlands grid transport is going to be charged per kWh, with a
tariff that depends on the month and the hour. It's paid on energy you
**buy**, not on energy you sell. ESS Manager therefore works with two
prices per 15-minute unit:

- **Sell price** = the price sensor's own price (the `all_price` attribute).
- **Buy price** = price + (transport tariff x factor for that unit) (the
  `all_buy_price` attribute).

Every buy decision uses the buy price: the low charge plan's window,
full-charge balancing's window, the negative price plan's trigger ("is
buying below the threshold?") and the spike plan's charge window. Every
sell decision uses the sell price: the high discharge plan, making room
before a negative price window, and the spike plan's discharge window. The
spike plan's gain is the day's highest sell price minus its lowest buy
price still ahead (a cheap quarter that's already past doesn't count,
unless the spike's charge has already run) divided by
the charge and discharge efficiency (so its
`day_min_price` is a buy price, `day_max_price` a sell price), and its
discharge price floor is that lowest buy price / the efficiencies plus the
margin. With prices including taxes (below) the buy prices are incl.

**The factors** (month x local hour) come with the integration in
`custom_components/ess_manager/transport_factors.json` - currently the draft
plan (winter: 0.5-0.7, 1.0 from 16:00 to 23:00; summer: 0.0 from 10:00 to
17:00, 0.3-0.7 otherwise). They're updated with the integration when the
plan changes; for a different table, fork the repository.

**The tariff** is the integration's own **Transport tariff** number entity
(on the ESS Manager device, default 0), in the same unit as your price
sensor and on the same basis (with or without VAT). At 0 the buy price is
the plain price and nothing changes; once the tariff is known, enter it
there. The Status sensor shows the value in use as `transport_tariff`.

## Prices including taxes

 The price sensor (e.g. Nordpool) gives the bare
market price; what you really pay per kWh also has the supplier's purchase
fee, the energy tax and VAT. Configure (page 1, **Prices including taxes**)
offers three choices:

- **No** (default) - the bare prices.
- **Enter them myself** - energy tax and purchase fee per kWh excl. VAT,
  and the VAT: incl = (price + purchase fee + energy tax) x (1 + VAT). The
  amounts are on your energy bill. Leave out the grid operator's fixed
  costs (a time-dependent grid tariff goes in the Transport tariff number).
- **Learn it from my supplier's price sensor** - any sensor whose state is
  the supplier's **current** price including taxes (EUR/kWh or ct/kWh, per
  quarter or per hour - e.g. the Zonneplan or Tibber integration's current
  tariff). Every quarter (minutes 5-12, so a sensor that changes a bit late
  isn't caught on the old price) its value is noted next to the bare price
  of that quarter, and the line incl = a x price + b is fitted to the last
  7 days. It's used once there's a day of quarters with at least 3 ct
  between the cheapest and dearest price and the line fits closely (with
  flat prices it waits); until then the prices stay bare. A supplier with
  hourly prices is compared per hour. A change of energy tax or fee (four
  quarters in a row more than 1 ct off the line) moves the line by itself.
  The learned quarters are stored apart (`ess_manager_<entry>_prices`), only
  when one is added.

**Counted as from 2027:** buying costs the price incl taxes (of price +
transport tariff, see "Grid transport tariff"), selling brings in the bare
price - as when net metering (salderen) ends in the Netherlands on
1 January 2027. Without prices incl taxes ("No") buying is price +
transport and selling the price.

The Status sensor carries `price_incl` (the way chosen, the line a / b, how
well it fits, how many quarters, or why it's still learning) and
`all_buy_price_incl`; the sell price is `all_price`.

**Every plan counts with them:** the low charge plan (which quarters to
buy, and whether taking the house from the grid now beats the battery
after its losses), the sale plan, full-charge balancing, Solar export and
the heat pump's buffer, and:

- **Negative price plan** - triggers when the **buy price incl** drops
  below your negative price threshold (with the line above: a bare price
  below about -0.11 gives a buy price incl below 0).
- **Spike plan** - the spike margin is the **real gain per kWh**: sell
  price in the peak minus buy price / (charge efficiency x discharge
  efficiency). A spike is only planned when that's above the margin; the
  top-up's price cap and the sale's price floor follow the same gain. The
  buy price is the cheapest one from now on: last night's low doesn't make
  a spike in the morning that would then charge at daytime prices.
