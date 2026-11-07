#pragma once
namespace aero_gate {
// A real implementation must obtain the *active* engine/detector instances,
// provider addresses and pre-step time without running a paused iteration.
// There is no public installed Sim API binding established for this yet.
bool LiveAdapterAvailable() noexcept;
}
