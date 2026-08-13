import "./home.css";
import background from "@/assets/b2_1786608771b8b1.png";

const APP_ENDPOINT = "/Text-to-Masterpiece";

const CTA_LABEL = "Create";

const PAGE_LABEL = "/ homepage";

export function Home() {
  return (
    <div className="home">
      <header className="home__top">{PAGE_LABEL}</header>

      <main className="home__main">
        <section className="home__left">
          <h1 className="home__title">
            <span className="home__upper">
              <span>Text</span>
              <span> to</span>
            </span>

            <span className="home__lower">
              <span>Masterpiece</span>
            </span>
          </h1>

          <a className="home__cta" href={APP_ENDPOINT}>
            {CTA_LABEL}
          </a>
        </section>

        <section className="home__right">
          <img
            src={background}
            className="home__art"
          />
        </section>
      </main>
    </div>
  );
}

export default Home;
