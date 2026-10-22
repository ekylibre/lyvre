// Liens et navigation entre pages de la SPA et anciennes pages Jinja (mêmes URL, FM3).
import { forwardRef, useCallback, type AnchorHTMLAttributes } from "react";
import { Link, useNavigate } from "react-router";
import { isSpaPath } from "./routes";

/** Navigation vers une URL : routeur si la page est dans la SPA, sinon chargement complet. */
export function useGoTo() {
  const navigate = useNavigate();
  return useCallback((url: string, options?: { replace?: boolean }) => {
    if (isSpaPath(url)) navigate(url, options);
    else if (options?.replace) window.location.replace(url);
    else window.location.assign(url);
  }, [navigate]);
}

type AppLinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & { href: string };

/** Lien interne : <Link> pour une page de la SPA, <a> pour une ancienne page. */
export const AppLink = forwardRef<HTMLAnchorElement, AppLinkProps>(function AppLink(
  { href, ...rest }, ref,
) {
  if (isSpaPath(href)) return <Link ref={ref} to={href} {...rest} />;
  return <a ref={ref} href={href} {...rest} />;
});
