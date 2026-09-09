import Head from "next/head";
import type { AppProps } from "next/app";
import store from "../redux/store";
import { Provider } from "react-redux";

// eslint-disable-next-line @typescript-eslint/naming-convention
const App = ({ Component, pageProps }: AppProps) => {
    return (
        <>
            <Head>
                <title> Conway&#39;s life game</title>
            </Head>
            <div style={{ padding: 12 }}>
                <Component {...pageProps} />
            </div>
        </>
    );
};

export default function AppWrapper(props: AppProps) {
    return (
        <Provider store={store}>
            <App {...props} />
        </Provider>
    );
}
