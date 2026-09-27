import { withStackInspect } from "@stack-inspect/next/middleware";
import { NextResponse } from "next/server";

export default withStackInspect(() => NextResponse.next());

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
