/**
 * Runs before React hydration so the DevTools hook can receive inject()
 * when React registers its renderer.
 */
import { installDevtoolsHook } from "@stack-inspect/react";

installDevtoolsHook();
